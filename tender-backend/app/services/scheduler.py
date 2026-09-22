"""The loop that runs scheduled scrapes.

It wakes every minute, finds schedules whose time has passed, and scrapes
those sites. Two things matter here:

  * **A schedule must not fire twice.** Running under `--reload`, or with more
    than one worker, means several processes may hold this loop. Before
    scraping, the runner moves `next_run_at` forward with a conditional
    update; only the process whose update actually changed a row proceeds. A
    second process finds nothing due and does nothing.

  * **A failure must not stop the loop.** One site erroring, or the database
    being briefly unreachable, is logged and the loop carries on. A scheduler
    that dies quietly is worse than one that occasionally misses a run.

The loop lives in the API process, which is fine at this scale and avoids
running a separate worker. If this ever needs to survive the API being down,
it should move to its own process.
"""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select, update

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.schedule import ScheduleGroup
from app.services.ingestion_service import run_ingestion
from app.services.schedule_service import compute_next_run

logger = logging.getLogger(__name__)

# How often to look for work. Schedules are set to the minute, so checking
# more often would only add load.
TICK_SECONDS = 60


async def _claim_due(now: datetime) -> list[tuple[int, str, list[int]]]:
    """Take ownership of every group that is due.

    Returns (group id, label, site ids) for each one claimed. Claiming is the
    conditional update: if another process got there first, `next_run_at` has
    already moved and the update matches nothing.

    Paused sites are filtered out here rather than in the scrape, so a group
    whose sites are all paused does not report a run that did nothing.
    """
    claimed: list[tuple[int, str, list[int]]] = []

    async with AsyncSessionLocal() as db:
        stmt = select(ScheduleGroup).where(
            ScheduleGroup.enabled.is_(True),
            ScheduleGroup.next_run_at.is_not(None),
            ScheduleGroup.next_run_at <= now,
        )
        for group in (await db.execute(stmt)).scalars().all():
            following = compute_next_run(
                group.frequency, group.run_at, interval_days=group.interval_days
            )
            result = await db.execute(
                update(ScheduleGroup)
                .where(
                    ScheduleGroup.id == group.id,
                    ScheduleGroup.next_run_at == group.next_run_at,
                )
                .values(next_run_at=following)
            )
            if result.rowcount:
                active = [s.id for s in group.sites if s.active]
                claimed.append((group.id, group.name or f"Schedule {group.id}", active))
        await db.commit()

    return claimed


async def _record(group_id: int, status: str, error: str | None) -> None:
    async with AsyncSessionLocal() as db:
        group = await db.get(ScheduleGroup, group_id)
        if group is not None:
            group.last_run_at = datetime.now(timezone.utc)
            group.last_status = status
            group.last_error = error[:500] if error else None
            await db.commit()


async def run_due(now: datetime | None = None) -> int:
    """Scrape every group that is due. Returns how many groups ran."""
    now = now or datetime.now(timezone.utc)
    claimed = await _claim_due(now)
    if not claimed:
        return 0

    logger.info("Scheduler: %s group(s) due", len(claimed))

    for group_id, label, site_ids in claimed:
        if not site_ids:
            await _record(group_id, "skipped", "Every site in this schedule is paused.")
            logger.info("Scheduler: %s skipped, all sites paused", label)
            continue

        try:
            result = await run_ingestion(site_ids=site_ids)
            totals = result.as_dict()["totals"]
            failed = totals["sites_failed"]
            if failed:
                first = next(s.error for s in result.sites if s.error)
                await _record(
                    group_id,
                    "failed",
                    f"{failed} of {len(site_ids)} site(s) failed. First: {first}",
                )
                logger.warning("Scheduler: %s had %s failure(s)", label, failed)
            else:
                await _record(group_id, "ok", None)
                logger.info(
                    "Scheduler: %s done, %s new tender(s) across %s site(s)",
                    label, totals["inserted"], len(site_ids),
                )
        except Exception as exc:  # noqa: BLE001 - one group must not stop the rest
            logger.exception("Scheduler: %s raised", label)
            await _record(group_id, "failed", f"{type(exc).__name__}: {exc}")

    return len(claimed)


async def scheduler_loop() -> None:
    """Check for due schedules until cancelled."""
    logger.info("Scheduler started, checking every %s seconds", TICK_SECONDS)
    while True:
        try:
            await run_due()
        except asyncio.CancelledError:
            logger.info("Scheduler stopping")
            raise
        except Exception:  # noqa: BLE001 - the loop must outlive any one failure
            logger.exception("Scheduler tick failed")
        await asyncio.sleep(TICK_SECONDS)


def start(app) -> None:
    """Attach the loop to the application lifespan."""
    if not settings.SCHEDULER_ENABLED:
        logger.info("Scheduler disabled by configuration")
        return
    app.state.scheduler_task = asyncio.create_task(scheduler_loop())


async def stop(app) -> None:
    task = getattr(app.state, "scheduler_task", None)
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
