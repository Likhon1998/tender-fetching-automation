from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BeforeValidator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.capabilities import TRIAGE_TENDERS
from app.core.deps import CurrentUser, require_capability
from app.db.session import get_db
from app.schemas.tender import TenderPage, TenderResponse, TenderStatusUpdate
from app.services import tender_service as svc

router = APIRouter(prefix="/tenders", tags=["tenders"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


def _blank_to_none(value):
    """Treat an empty query value as absent.

    Browsers submit `category_id=` for an unselected dropdown, and rejecting
    that with a 422 would be unhelpful when the intent is clearly "no filter".
    """
    return None if value == "" else value


OptionalId = Annotated[int | None, BeforeValidator(_blank_to_none)]
OptionalDate = Annotated[date | None, BeforeValidator(_blank_to_none)]


@router.get("", response_model=TenderPage, summary="Browse tenders")
async def list_tenders(
    db: DbSession,
    current_user: CurrentUser,
    search: Annotated[str | None, Query(description="Match against the title")] = None,
    category_id: OptionalId = None,
    site_id: OptionalId = None,
    status_filter: Annotated[
        Literal["new", "not_interested", "all"],
        Query(alias="status", description="Triage state; 'all' shows both"),
    ] = "new",
    date_from: OptionalDate = None,
    date_to: OptionalDate = None,
    uncategorised: Annotated[
        Literal["exclude", "include", "only"],
        Query(
            description="Notices the classifier could not place: hide them, "
            "mix them in, or show only those."
        ),
    ] = "exclude",
    scope: Annotated[
        Literal["saved", "unsaved", "all"],
        Query(
            description="'saved' shows only tenders kept in a list, "
            "'unsaved' only those not yet in one, 'all' everything scraped."
        ),
    ] = "saved",
    submission_within: Annotated[
        Literal["1", "2", "3", "4", "4plus"] | None,
        Query(
            description="Deadline falling within this many weeks. "
            "'4plus' means more than four weeks away. Notices with no known "
            "deadline, and deadlines already passed, are excluded."
        ),
    ] = None,
    sort: Literal["date", "submission_date", "title", "confidence", "created_at"] = "date",
    order: Literal["asc", "desc"] = "desc",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 25,
) -> TenderPage:
    """Search, filter and sort the tender registry.

    Dismissed tenders are hidden by default; pass `status=not_interested` to
    review them or `status=all` for everything.

    Notices the classifier could not place are hidden by default. Pass
    `uncategorised=include` to mix them in, or `uncategorised=only` to review
    just those, which is the quickest way to spot gaps in the keyword lists.

    Only tenders saved to a list are shown. Pass `scope=unsaved` for the
    review inbox of everything a scrape brought in that nobody has kept yet,
    or `scope=all` for both.
    """
    rows, total = await svc.search_tenders(
        db,
        search=search,
        category_id=category_id,
        site_id=site_id,
        status=None if status_filter == "all" else status_filter,
        date_from=date_from,
        date_to=date_to,
        uncategorised=uncategorised,
        scope=scope,
        submission_within=submission_within,
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
    )

    return TenderPage(
        items=[TenderResponse.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
        pages=max(1, -(-total // page_size)),
    )


@router.get("/summary", summary="Counts by triage state")
async def tender_summary(
    db: DbSession,
    current_user: CurrentUser,
    scope: Annotated[Literal["saved", "unsaved", "all"], Query()] = "saved",
) -> dict:
    return await svc.count_by_status(db, scope=scope)


@router.get("/ids", summary="Every tender id matching these filters")
async def tender_ids(
    db: DbSession,
    current_user: CurrentUser,
    search: str | None = None,
    category_id: OptionalId = None,
    site_id: OptionalId = None,
    status_filter: Annotated[
        Literal["new", "not_interested", "all"], Query(alias="status")
    ] = "new",
    uncategorised: Annotated[Literal["exclude", "include", "only"], Query()] = "exclude",
    scope: Annotated[Literal["saved", "unsaved", "all"], Query()] = "unsaved",
) -> dict:
    """Results are paginated, so "select all" needs the whole set, not a page."""
    rows, total = await svc.search_tenders(
        db,
        search=search,
        category_id=category_id,
        site_id=site_id,
        status=None if status_filter == "all" else status_filter,
        uncategorised=uncategorised,
        scope=scope,
        page=1,
        page_size=5000,
    )
    return {"tender_ids": [t.id for t in rows], "count": total}


@router.get("/{tender_id}", response_model=TenderResponse, summary="Get one tender")
async def get_tender(tender_id: int, db: DbSession, current_user: CurrentUser):
    try:
        return await svc.get_one(db, tender_id)
    except svc.NotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tender not found")


@router.patch(
    "/{tender_id}",
    response_model=TenderResponse,
    dependencies=[Depends(require_capability(TRIAGE_TENDERS))],
    summary="Mark a tender as not interested, or restore it",
)
async def update_tender_status(
    tender_id: int,
    payload: TenderStatusUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Needs the triage capability: some accounts are read-only by design."""
    try:
        return await svc.set_status(db, tender_id, payload.status)
    except svc.NotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tender not found")
