"""Query and triage logic for tenders.

Filtering lives here rather than in the ingestion pipeline: every notice is
stored, and the browse endpoint decides what to show. That keeps the date
cutoff and relevance rules changeable without re-scraping.
"""

from datetime import date, timedelta

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

# Aliased: this module already has a function called search_tenders.
from app.models.search import Search
from app.models.search import search_tenders as search_tenders_table
from app.models.tender import STATUS_NEW, Tender

SORTABLE = {
    "date": Tender.date,
    "submission_date": Tender.submission_date,
    "title": Tender.title,
    "confidence": Tender.confidence,
    "created_at": Tender.created_at,
}


class NotFound(Exception):
    pass


class DuplicateTitle(Exception):
    pass


def _apply_filters(
    stmt: Select,
    *,
    search: str | None,
    category_id: int | None,
    site_id: int | None,
    status: str | None,
    date_from: date | None,
    date_to: date | None,
    uncategorised: str,
    scope: str,
    submission_within: str | None,
) -> Select:
    if search:
        stmt = stmt.where(Tender.title.ilike(f"%{search.strip()}%"))
    if category_id is not None:
        stmt = stmt.where(Tender.category_id == category_id)
    if site_id is not None:
        stmt = stmt.where(Tender.site_id == site_id)
    if status is not None:
        stmt = stmt.where(Tender.status == status)

    # Undated notices are kept by any date filter. A missing date means the
    # source did not publish one, not that the notice is old, and dropping
    # them would silently lose tenders from sites that never show dates.
    if date_from is not None:
        stmt = stmt.where(or_(Tender.date.is_(None), Tender.date >= date_from))
    if date_to is not None:
        stmt = stmt.where(or_(Tender.date.is_(None), Tender.date <= date_to))

    # Notices the classifier could not place are hidden by default, shown
    # alongside the rest with "include", or shown on their own with "only".
    # Seeing them on their own is how you tell whether the keyword lists are
    # missing something.
    # Three views of the same table. "saved" is the curated registry, what
    # people chose to keep. "unsaved" is the review inbox: everything a
    # scheduled scrape brought in that nobody has looked at yet. "all" is both.
    in_a_list = (
        select(search_tenders_table.c.tender_id)
        .join(Search, Search.id == search_tenders_table.c.search_id)
        .where(Search.saved.is_(True))
    )
    if scope == "saved":
        stmt = stmt.where(Tender.id.in_(in_a_list))
    elif scope == "unsaved":
        stmt = stmt.where(Tender.id.not_in(in_a_list))

    # "Submission within" only makes sense for notices whose deadline we know,
    # and a deadline that has already passed is of no use, so both are
    # excluded rather than shown as near-term.
    if submission_within:
        today = date.today()
        stmt = stmt.where(
            Tender.submission_date.is_not(None), Tender.submission_date >= today
        )
        if submission_within == "4plus":
            stmt = stmt.where(Tender.submission_date > today + timedelta(weeks=4))
        else:
            weeks = int(submission_within)
            stmt = stmt.where(Tender.submission_date <= today + timedelta(weeks=weeks))

    if uncategorised == "exclude":
        stmt = stmt.where(Tender.category_id.is_not(None))
    elif uncategorised == "only":
        stmt = stmt.where(Tender.category_id.is_(None))

    return stmt


async def search_tenders(
    db: AsyncSession,
    *,
    search: str | None = None,
    category_id: int | None = None,
    site_id: int | None = None,
    status: str | None = STATUS_NEW,
    date_from: date | None = None,
    date_to: date | None = None,
    uncategorised: str = "exclude",
    scope: str = "saved",
    submission_within: str | None = None,
    sort: str = "date",
    order: str = "desc",
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[Tender], int]:
    filters = dict(
        search=search,
        category_id=category_id,
        site_id=site_id,
        status=status,
        date_from=date_from,
        date_to=date_to,
        uncategorised=uncategorised,
        scope=scope,
        submission_within=submission_within,
    )

    count_stmt = _apply_filters(select(func.count()).select_from(Tender), **filters)
    total = (await db.execute(count_stmt)).scalar_one()

    column = SORTABLE.get(sort, Tender.date)
    direction = column.asc() if order == "asc" else column.desc()

    stmt = _apply_filters(select(Tender), **filters)
    # Undated rows sort last regardless of direction, and id breaks ties so
    # pagination stays stable across requests.
    stmt = stmt.order_by(direction.nullslast(), Tender.id.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    rows = list((await db.execute(stmt)).scalars().all())
    return rows, total


async def get_one(db: AsyncSession, tender_id: int) -> Tender:
    row = await db.get(Tender, tender_id)
    if row is None:
        raise NotFound()
    return row


async def set_status(db: AsyncSession, tender_id: int, status: str) -> Tender:
    row = await get_one(db, tender_id)
    row.status = status
    await db.commit()
    await db.refresh(row)
    return row


async def title_exists(db: AsyncSession, title: str) -> bool:
    stmt = select(Tender.id).where(Tender.title == title).limit(1)
    return (await db.execute(stmt)).scalar_one_or_none() is not None


async def create(db: AsyncSession, data: dict) -> Tender:
    """Insert one tender. Raises DuplicateTitle rather than relying on the
    unique constraint to blow up, so the caller can count skips cleanly."""
    if await title_exists(db, data["title"]):
        raise DuplicateTitle()
    row = Tender(**data)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def count_by_status(db: AsyncSession, scope: str = "saved") -> dict:
    """Counts for the registry header, over the same set the page shows."""
    saved_ids = (
        select(search_tenders_table.c.tender_id)
        .join(Search, Search.id == search_tenders_table.c.search_id)
        .where(Search.saved.is_(True))
    )

    stmt = select(Tender.status, func.count()).group_by(Tender.status)
    unclassified_stmt = (
        select(func.count()).select_from(Tender).where(Tender.category_id.is_(None))
    )
    if scope == "saved":
        stmt = stmt.where(Tender.id.in_(saved_ids))
        unclassified_stmt = unclassified_stmt.where(Tender.id.in_(saved_ids))
    elif scope == "unsaved":
        stmt = stmt.where(Tender.id.not_in(saved_ids))
        unclassified_stmt = unclassified_stmt.where(Tender.id.not_in(saved_ids))

    by_status = {s: c for s, c in (await db.execute(stmt)).all()}
    unclassified = (await db.execute(unclassified_stmt)).scalar_one()

    return {
        "total": sum(by_status.values()),
        "by_status": by_status,
        "unclassified": unclassified,
    }
