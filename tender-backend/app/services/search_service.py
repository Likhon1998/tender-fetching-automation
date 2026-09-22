"""The search wizard: choose sites, choose categories, scrape, then save.

A search scrapes the selected sites when it runs, rather than reading a
weekly batch. That keeps results current at the cost of a few minutes per run,
so the scrape happens in the background and the wizard polls for progress.

Results are shown as soon as the scrape finishes. Nothing is kept until the
user ticks the tenders worth keeping and saves them, which is what turns a
search into a saved list.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import case, delete, func, insert, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.category import Category
from app.models.search import Search, SearchStatus, search_tenders
from app.models.site import Site
from app.models.tender import Tender
from app.services.ingestion_service import run_ingestion

logger = logging.getLogger(__name__)


class NotFound(Exception):
    pass


class NothingSelected(Exception):
    pass


class NotReady(Exception):
    """The scrape is still running, so there is nothing to save yet."""


async def create_search(
    db: AsyncSession,
    *,
    site_ids: list[int],
    category_ids: list[int],
    include_uncategorised: bool = False,
    user=None,
) -> Search:
    """Record the selection. The caller starts the scrape in the background."""
    if not site_ids:
        raise NothingSelected("Select at least one site.")
    if not category_ids and not include_uncategorised:
        raise NothingSelected("Select at least one category.")

    sites = (
        await db.execute(
            select(Site.id, Site.name).where(Site.id.in_(site_ids)).order_by(Site.name)
        )
    ).all()
    if len(sites) != len(set(site_ids)):
        raise NotFound("One or more selected sites no longer exist.")

    categories = []
    if category_ids:
        categories = (
            await db.execute(
                select(Category.id, Category.name)
                .where(Category.id.in_(category_ids))
                .order_by(Category.name)
            )
        ).all()
        if len(categories) != len(set(category_ids)):
            raise NotFound("One or more selected categories no longer exist.")

    search = Search(
        created_by=getattr(user, "id", None),
        created_by_username=getattr(user, "username", None),
        site_ids=[s.id for s in sites],
        site_names=[s.name for s in sites],
        category_ids=[c.id for c in categories],
        category_names=[c.name for c in categories],
        include_uncategorised=include_uncategorised,
        status=SearchStatus.PENDING.value,
        sites_total=len(sites),
    )
    db.add(search)
    await db.commit()
    await db.refresh(search)
    return search


async def run_search(search_id: int) -> None:
    """Scrape the chosen sites. Intended to run in the background."""
    async with AsyncSessionLocal() as db:
        search = await db.get(Search, search_id)
        if search is None:
            logger.warning("Search %s vanished before it could run", search_id)
            return
        site_ids = list(search.site_ids)
        search.status = SearchStatus.RUNNING.value
        search.started_at = datetime.now(timezone.utc)
        search.sites_done = 0
        await db.commit()

    async def on_site_done(name: str, done: int, total: int) -> None:
        async with AsyncSessionLocal() as progress_db:
            row = await progress_db.get(Search, search_id)
            if row is not None:
                row.sites_done = done
                row.sites_total = total
                row.current_site = name
                await progress_db.commit()

    try:
        await run_ingestion(site_ids=site_ids, on_site_done=on_site_done)

        async with AsyncSessionLocal() as db:
            search = await db.get(Search, search_id)
            search.status = SearchStatus.COMPLETED.value
            search.current_site = None
            search.sites_done = search.sites_total
            search.finished_at = datetime.now(timezone.utc)
            await db.commit()
        logger.info("Search %s finished scraping", search_id)

    except Exception as exc:  # noqa: BLE001 - the search reports its own failure
        logger.exception("Search %s failed", search_id)
        async with AsyncSessionLocal() as db:
            search = await db.get(Search, search_id)
            if search is not None:
                search.status = SearchStatus.FAILED.value
                search.error = f"{type(exc).__name__}: {exc}"[:500]
                search.finished_at = datetime.now(timezone.utc)
                await db.commit()


def _matches_selection(search: Search):
    """The filter a search's chosen sites and categories describe."""
    conditions = [Tender.site_id.in_(search.site_ids)]

    category_match = []
    if search.category_ids:
        category_match.append(Tender.category_id.in_(search.category_ids))
    if search.include_uncategorised:
        category_match.append(Tender.category_id.is_(None))
    if category_match:
        conditions.append(or_(*category_match))

    return conditions


async def already_saved_ids(
    db: AsyncSession, tender_ids: list[int], *, excluding_search: int | None = None
) -> set[int]:
    """Of these tenders, which are already in a saved list.

    A tender belongs in one list only: seeing the same notice twice across
    lists is confusing, and the second copy carries no new information.
    """
    if not tender_ids:
        return set()

    stmt = (
        select(search_tenders.c.tender_id)
        .join(Search, Search.id == search_tenders.c.search_id)
        .where(search_tenders.c.tender_id.in_(tender_ids), Search.saved.is_(True))
    )
    if excluding_search is not None:
        stmt = stmt.where(search_tenders.c.search_id != excluding_search)
    return set((await db.execute(stmt)).scalars().all())


async def save_selection(
    db: AsyncSession, search_id: int, tender_ids: list[int]
) -> Search:
    """Keep the tenders the user ticked, and mark the search as a saved list.

    Saving again replaces the previous selection, so a user can revisit a list
    and change their mind without ending up with duplicates.
    """
    search = await get_search(db, search_id)
    if search.status != SearchStatus.COMPLETED.value:
        raise NotReady("The search has not finished yet.")

    # Only accept tenders this search actually turned up. Anything else would
    # let a client attach arbitrary rows to a saved list.
    allowed = set(
        (await db.execute(select(Tender.id).where(*_matches_selection(search))))
        .scalars()
        .all()
    )
    requested = [tid for tid in dict.fromkeys(tender_ids) if tid in allowed]

    # Drop anything already kept in another list rather than failing the whole
    # save: the user may have ticked select all without noticing.
    duplicates = await already_saved_ids(db, requested, excluding_search=search_id)
    chosen = [tid for tid in requested if tid not in duplicates]

    await db.execute(
        delete(search_tenders).where(search_tenders.c.search_id == search_id)
    )
    if chosen:
        await db.execute(
            insert(search_tenders),
            [{"search_id": search_id, "tender_id": tid} for tid in chosen],
        )

    search.tender_count = len(chosen)
    search.saved = True
    search.saved_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(search)

    logger.info(
        "Search %s saved with %s tender(s), %s already in another list",
        search_id, len(chosen), len(duplicates),
    )
    return search


async def list_from_tenders(
    db: AsyncSession, tender_ids: list[int], *, name: str | None = None, user=None
) -> Search:
    """Turn a hand-picked set of tenders into a saved list.

    Scheduled scrapes store tenders without anyone having asked for them, so
    there has to be a way to keep some of what turns up without re-running a
    search. The sites and categories are taken from the tenders themselves, so
    a list made this way reads the same as one made from a search.
    """
    if not tender_ids:
        raise NothingSelected("Select at least one tender.")

    already = await already_saved_ids(db, tender_ids)
    wanted = [tid for tid in dict.fromkeys(tender_ids) if tid not in already]
    if not wanted:
        raise NothingSelected("Every selected tender is already in a list.")

    rows = list(
        (await db.execute(select(Tender).where(Tender.id.in_(wanted)))).scalars().all()
    )
    if len(rows) != len(wanted):
        raise NotFound("One or more selected tenders no longer exist.")

    site_ids = sorted({t.site_id for t in rows if t.site_id is not None})
    site_names = sorted({t.source_name for t in rows if t.source_name})
    category_ids = sorted({t.category_id for t in rows if t.category_id is not None})
    category_names = sorted({t.category for t in rows if t.category})

    now = datetime.now(timezone.utc)
    search = Search(
        created_by=getattr(user, "id", None),
        created_by_username=getattr(user, "username", None),
        site_ids=site_ids,
        site_names=site_names,
        category_ids=category_ids,
        category_names=category_names,
        include_uncategorised=any(t.category_id is None for t in rows),
        status=SearchStatus.COMPLETED.value,
        sites_total=len(site_ids),
        sites_done=len(site_ids),
        started_at=now,
        finished_at=now,
        saved=True,
        saved_at=now,
        tender_count=len(rows),
    )
    db.add(search)
    await db.flush()
    await db.execute(
        insert(search_tenders),
        [{"search_id": search.id, "tender_id": t.id} for t in rows],
    )
    await db.commit()
    await db.refresh(search)
    logger.info("Created list %s from %s reviewed tender(s)", search.id, len(rows))
    return search


async def add_to_list(
    db: AsyncSession, search_id: int, tender_ids: list[int]
) -> Search:
    """Append tenders to a list that already exists."""
    search = await get_search(db, search_id)
    if not search.saved:
        raise NotReady("That search has not been saved as a list yet.")

    already = await already_saved_ids(db, tender_ids)
    wanted = [tid for tid in dict.fromkeys(tender_ids) if tid not in already]
    if not wanted:
        raise NothingSelected("Every selected tender is already in a list.")

    rows = list(
        (await db.execute(select(Tender).where(Tender.id.in_(wanted)))).scalars().all()
    )
    await db.execute(
        insert(search_tenders),
        [{"search_id": search_id, "tender_id": t.id} for t in rows],
    )

    # Widen the recorded sites and categories to cover what was added, so the
    # list still describes its own contents.
    search.site_ids = sorted(set(search.site_ids) | {t.site_id for t in rows if t.site_id})
    search.site_names = sorted(
        set(search.site_names) | {t.source_name for t in rows if t.source_name}
    )
    search.category_ids = sorted(
        set(search.category_ids) | {t.category_id for t in rows if t.category_id}
    )
    search.category_names = sorted(
        set(search.category_names) | {t.category for t in rows if t.category}
    )
    if any(t.category_id is None for t in rows):
        search.include_uncategorised = True
    search.tender_count = search.tender_count + len(rows)

    await db.commit()
    await db.refresh(search)
    return search


async def get_search(db: AsyncSession, search_id: int) -> Search:
    search = await db.get(Search, search_id)
    if search is None:
        raise NotFound("Search not found")
    return search


async def list_searches(db: AsyncSession, limit: int = 50) -> list[Search]:
    """Saved lists only. Abandoned searches are noise, not history."""
    stmt = (
        select(Search)
        .where(Search.saved.is_(True))
        .order_by(Search.created_at.desc(), Search.id.desc())
        .limit(limit)
    )
    return list((await db.execute(stmt)).scalars().all())


async def delete_search(db: AsyncSession, search_id: int) -> None:
    """Remove a saved list. The tenders themselves are untouched."""
    search = await get_search(db, search_id)
    await db.delete(search)
    await db.commit()


async def search_results(
    db: AsyncSession,
    search_id: int,
    *,
    search_text: str | None = None,
    status: str | None = None,
    sort: str = "date",
    order: str = "desc",
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[Tender], int]:
    """What to show for a search.

    Before it is saved, that is everything the scrape turned up matching the
    chosen sites and categories. Afterwards it is the tenders the user kept.
    """
    search = await get_search(db, search_id)

    if search.saved:
        base = (
            select(Tender)
            .join(search_tenders, search_tenders.c.tender_id == Tender.id)
            .where(search_tenders.c.search_id == search_id)
        )
        count_stmt = (
            select(func.count())
            .select_from(search_tenders)
            .join(Tender, Tender.id == search_tenders.c.tender_id)
            .where(search_tenders.c.search_id == search_id)
        )
    else:
        conditions = _matches_selection(search)
        base = select(Tender).where(*conditions)
        count_stmt = select(func.count()).select_from(Tender).where(*conditions)

    if search_text:
        needle = f"%{search_text.strip()}%"
        base = base.where(Tender.title.ilike(needle))
        count_stmt = count_stmt.where(Tender.title.ilike(needle))
    if status:
        base = base.where(Tender.status == status)
        count_stmt = count_stmt.where(Tender.status == status)

    total = (await db.execute(count_stmt)).scalar_one()

    columns = {
        "date": Tender.date,
        "title": Tender.title,
        "confidence": Tender.confidence,
        "created_at": Tender.created_at,
    }
    column = columns.get(sort, Tender.date)
    direction = column.asc() if order == "asc" else column.desc()

    stmt = (
        base.order_by(
            case((column.is_(None), 1), else_=0),
            direction,
            Tender.id.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list((await db.execute(stmt)).scalars().all()), total


async def all_result_ids(db: AsyncSession, search_id: int) -> list[int]:
    """Every tender id in a search, for the "select all" action.

    The results screen is paginated, so ticking select all has to mean the
    whole result set rather than just the visible page.
    """
    search = await get_search(db, search_id)
    if search.saved:
        stmt = select(search_tenders.c.tender_id).where(
            search_tenders.c.search_id == search_id
        )
    else:
        stmt = select(Tender.id).where(*_matches_selection(search))
    return list((await db.execute(stmt)).scalars().all())
