"""Schedule groups: sets of sites scraped together on the same cadence.

Times are stored as wall-clock times in the configured timezone rather than
UTC. A group set for 08:00 should stay at 08:00 for the people reading it, so
the local time is what is kept and the UTC instant is derived from it.

A site belongs to at most one group. Two groups covering the same site would
scrape it twice on overlapping days and leave no clear answer to "when is this
site next fetched", so the constraint is enforced in the database and surfaced
in the interface rather than being left to chance.
"""

import calendar
import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.schedule import (
    INTERVAL_DAYS,
    Frequency,
    ScheduleGroup,
    schedule_group_sites,
)
from app.models.site import Site

logger = logging.getLogger(__name__)


class NotFound(Exception):
    pass


class InvalidSchedule(Exception):
    pass


class SiteAlreadyScheduled(Exception):
    """One or more chosen sites already belong to another group."""

    def __init__(self, clashes: list[dict]):
        self.clashes = clashes
        names = ", ".join(c["site_name"] for c in clashes)
        super().__init__(
            f"Already in another schedule group: {names}. "
            "Remove them from that group first."
        )


def local_zone() -> ZoneInfo:
    return ZoneInfo(settings.TIMEZONE)


def _add_month(moment: datetime) -> datetime:
    """Same day next month, clamped to the length of that month.

    A group set for the 31st runs on the 30th in November and the 28th in
    February rather than skipping those months entirely.
    """
    year = moment.year + (moment.month // 12)
    month = moment.month % 12 + 1
    day = min(moment.day, calendar.monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)


def compute_next_run(
    frequency: str,
    run_at: time,
    *,
    interval_days: int | None = None,
    after: datetime | None = None,
) -> datetime:
    """The next UTC instant this group should fire.

    The result is always strictly in the future, so a group whose time has
    already gone today runs tomorrow rather than immediately.
    """
    zone = local_zone()
    now = (after or datetime.now(zone)).astimezone(zone)
    candidate = now.replace(
        hour=run_at.hour, minute=run_at.minute, second=0, microsecond=0
    )

    if frequency == Frequency.MONTHLY.value:
        if candidate <= now:
            candidate = _add_month(candidate)
        return candidate.astimezone(ZoneInfo("UTC"))

    if frequency == Frequency.CUSTOM.value:
        if not interval_days or interval_days < 1:
            raise InvalidSchedule(
                "A custom schedule needs an interval of at least one day."
            )
        step = interval_days
    else:
        try:
            step = INTERVAL_DAYS[Frequency(frequency)]
        except (KeyError, ValueError) as exc:
            raise InvalidSchedule(f"Unknown frequency {frequency!r}") from exc

    while candidate <= now:
        candidate += timedelta(days=step)

    return candidate.astimezone(ZoneInfo("UTC"))


async def site_availability(db: AsyncSession) -> list[dict]:
    """Every site, and which group already holds it.

    Drives the site picker: sites already spoken for are shown greyed out with
    the group named, rather than being hidden or silently failing on save.
    """
    stmt = (
        select(Site, ScheduleGroup)
        .outerjoin(
            schedule_group_sites, schedule_group_sites.c.site_id == Site.id
        )
        .outerjoin(
            ScheduleGroup, ScheduleGroup.id == schedule_group_sites.c.group_id
        )
        .order_by(Site.name)
    )
    rows = (await db.execute(stmt)).all()
    return [
        {
            "site_id": site.id,
            "site_name": site.name,
            "site_url": site.url,
            "site_active": site.active,
            "group_id": group.id if group else None,
            "group_name": (group.name or f"Schedule {group.id}") if group else None,
        }
        for site, group in rows
    ]


async def _check_free(
    db: AsyncSession, site_ids: list[int], *, excluding_group: int | None = None
) -> None:
    """Raise if any of these sites already belongs to a different group."""
    stmt = (
        select(Site.id, Site.name, ScheduleGroup.id, ScheduleGroup.name)
        .join(schedule_group_sites, schedule_group_sites.c.site_id == Site.id)
        .join(ScheduleGroup, ScheduleGroup.id == schedule_group_sites.c.group_id)
        .where(Site.id.in_(site_ids))
    )
    if excluding_group is not None:
        stmt = stmt.where(ScheduleGroup.id != excluding_group)

    clashes = [
        {
            "site_id": sid,
            "site_name": sname,
            "group_id": gid,
            "group_name": gname or f"Schedule {gid}",
        }
        for sid, sname, gid, gname in (await db.execute(stmt)).all()
    ]
    if clashes:
        raise SiteAlreadyScheduled(clashes)


async def _set_sites(db: AsyncSession, group_id: int, site_ids: list[int]) -> None:
    await db.execute(
        delete(schedule_group_sites).where(
            schedule_group_sites.c.group_id == group_id
        )
    )
    if site_ids:
        await db.execute(
            insert(schedule_group_sites),
            [{"group_id": group_id, "site_id": sid} for sid in dict.fromkeys(site_ids)],
        )


async def list_groups(db: AsyncSession) -> list[ScheduleGroup]:
    stmt = select(ScheduleGroup).order_by(
        ScheduleGroup.created_at.desc(), ScheduleGroup.id.desc()
    )
    return list((await db.execute(stmt)).scalars().all())


async def get_group(db: AsyncSession, group_id: int) -> ScheduleGroup:
    group = await db.get(ScheduleGroup, group_id)
    if group is None:
        raise NotFound("Schedule not found")
    return group


async def create_group(
    db: AsyncSession,
    *,
    site_ids: list[int],
    frequency: str,
    run_at: time,
    name: str | None = None,
    interval_days: int | None = None,
    enabled: bool = True,
) -> ScheduleGroup:
    if not site_ids:
        raise InvalidSchedule("Select at least one site.")
    if frequency == Frequency.CUSTOM.value and (not interval_days or interval_days < 1):
        raise InvalidSchedule("A custom schedule needs an interval of at least one day.")

    found = (
        await db.execute(select(Site.id).where(Site.id.in_(site_ids)))
    ).scalars().all()
    if len(set(found)) != len(set(site_ids)):
        raise NotFound("One or more selected sites no longer exist.")

    await _check_free(db, site_ids)

    group = ScheduleGroup(
        name=(name or "").strip() or None,
        frequency=frequency,
        interval_days=interval_days if frequency == Frequency.CUSTOM.value else None,
        run_at=run_at,
        enabled=enabled,
        next_run_at=compute_next_run(frequency, run_at, interval_days=interval_days)
        if enabled
        else None,
    )
    db.add(group)
    await db.flush()
    await _set_sites(db, group.id, site_ids)
    await db.commit()
    await db.refresh(group)
    return group


async def update_group(
    db: AsyncSession, group_id: int, changes: dict
) -> ScheduleGroup:
    group = await get_group(db, group_id)

    frequency = changes.get("frequency", group.frequency)
    run_at = changes.get("run_at", group.run_at)
    interval_days = changes.get("interval_days", group.interval_days)
    enabled = changes.get("enabled", group.enabled)

    if frequency == Frequency.CUSTOM.value and (not interval_days or interval_days < 1):
        raise InvalidSchedule("A custom schedule needs an interval of at least one day.")

    if "site_ids" in changes:
        site_ids = changes["site_ids"]
        if not site_ids:
            raise InvalidSchedule("A schedule needs at least one site.")
        found = (
            await db.execute(select(Site.id).where(Site.id.in_(site_ids)))
        ).scalars().all()
        if len(set(found)) != len(set(site_ids)):
            raise NotFound("One or more selected sites no longer exist.")
        await _check_free(db, site_ids, excluding_group=group_id)
        await _set_sites(db, group_id, site_ids)

    if "name" in changes:
        group.name = (changes["name"] or "").strip() or None

    group.frequency = frequency
    group.run_at = run_at
    group.interval_days = (
        interval_days if frequency == Frequency.CUSTOM.value else None
    )
    group.enabled = enabled

    # Timing changed, so the pending run is recalculated rather than keeping
    # an instant that no longer matches the settings.
    group.next_run_at = (
        compute_next_run(frequency, run_at, interval_days=group.interval_days)
        if enabled
        else None
    )

    await db.commit()
    await db.refresh(group)
    return group


async def delete_group(db: AsyncSession, group_id: int) -> None:
    """Remove a group. Its sites become available to other groups."""
    group = await get_group(db, group_id)
    await db.delete(group)
    await db.commit()
