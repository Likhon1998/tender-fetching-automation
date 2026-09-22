from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.capabilities import SAVE_LISTS, SEARCH_TENDERS
from app.core.deps import CurrentUser, require_capability
from app.db.session import get_db
from app.schemas.search import (
    ListFromTenders,
    SaveSelection,
    SearchCreate,
    SearchResponse,
    SearchResultsPage,
    SortField,
    SortOrder,
)
from app.schemas.tender import TenderResponse
from app.services import search_service as svc

router = APIRouter(
    prefix="/searches",
    tags=["searches"],
    dependencies=[Depends(require_capability(SEARCH_TENDERS))],
)

DbSession = Annotated[AsyncSession, Depends(get_db)]
CanSave = Depends(require_capability(SAVE_LISTS))


@router.post(
    "",
    response_model=SearchResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start a search: scrape the chosen sites",
)
async def create_search(
    payload: SearchCreate,
    background: BackgroundTasks,
    db: DbSession,
    current_user: CurrentUser,
) -> SearchResponse:
    """Record the selection and start scraping in the background.

    Scraping takes minutes, far longer than an HTTP request should stay open,
    so this returns immediately. Poll `GET /searches/{id}` for progress.
    """
    try:
        search = await svc.create_search(
            db,
            site_ids=payload.site_ids,
            category_ids=payload.category_ids,
            include_uncategorised=payload.include_uncategorised,
            user=current_user,
        )
    except svc.NothingSelected as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    except svc.NotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))

    background.add_task(svc.run_search, search.id)
    return SearchResponse.model_validate(search)


@router.post(
    "/from-tenders",
    response_model=SearchResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[CanSave],
    summary="Keep reviewed tenders as a list",
)
async def list_from_tenders(
    payload: ListFromTenders, db: DbSession, current_user: CurrentUser
) -> SearchResponse:
    """Turn tenders picked out of the review inbox into a saved list.

    Scheduled scrapes store tenders nobody asked for, so this is how anything
    worth keeping gets kept without re-running a search. Pass `search_id` to
    add to an existing list instead of starting a new one.
    """
    try:
        if payload.search_id is not None:
            search = await svc.add_to_list(db, payload.search_id, payload.tender_ids)
        else:
            search = await svc.list_from_tenders(
                db, payload.tender_ids, user=current_user
            )
    except svc.NothingSelected as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    except svc.NotReady as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except svc.NotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    return SearchResponse.model_validate(search)


@router.get("", response_model=list[SearchResponse], summary="Saved lists")
async def list_searches(
    db: DbSession,
    current_user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[SearchResponse]:
    rows = await svc.list_searches(db, limit=limit)
    return [SearchResponse.model_validate(r) for r in rows]


@router.get("/{search_id}", response_model=SearchResponse, summary="Search progress")
async def get_search(search_id: int, db: DbSession, current_user: CurrentUser):
    """Poll this while the scrape runs to drive the progress bar."""
    try:
        return await svc.get_search(db, search_id)
    except svc.NotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Search not found")


@router.post(
    "/{search_id}/save",
    response_model=SearchResponse,
    dependencies=[CanSave],
    summary="Save the selected tenders as a list",
)
async def save_selection(
    search_id: int, payload: SaveSelection, db: DbSession, current_user: CurrentUser
):
    """Keep the ticked tenders. Saving again replaces the earlier selection."""
    try:
        return await svc.save_selection(db, search_id, payload.tender_ids)
    except svc.NotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Search not found")
    except svc.NotReady as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))


@router.get(
    "/{search_id}/tender-ids",
    summary="Every tender id in this search, for select all",
)
async def result_ids(
    search_id: int, db: DbSession, current_user: CurrentUser
) -> dict:
    """Results are paginated, so "select all" needs the whole set, not a page."""
    try:
        ids = await svc.all_result_ids(db, search_id)
        # Select all must not tick tenders that cannot be saved.
        duplicates = await svc.already_saved_ids(db, ids, excluding_search=search_id)
    except svc.NotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Search not found")

    selectable = [tid for tid in ids if tid not in duplicates]
    return {
        "tender_ids": selectable,
        "count": len(selectable),
        "already_saved": sorted(duplicates),
    }


@router.delete(
    "/{search_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[CanSave],
    summary="Delete a saved list",
)
async def delete_search(
    search_id: int, db: DbSession, current_user: CurrentUser
) -> Response:
    """Removes the list only. The tenders it holds stay in the registry."""
    try:
        await svc.delete_search(db, search_id)
    except svc.NotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Search not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{search_id}/tenders",
    response_model=SearchResultsPage,
    summary="The tenders this search found",
)
async def get_search_results(
    search_id: int,
    db: DbSession,
    current_user: CurrentUser,
    search: str | None = None,
    status_filter: Annotated[
        str, Query(alias="status", pattern="^(new|not_interested|all)$")
    ] = "new",
    sort: SortField = "date",
    order: SortOrder = "desc",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 25,
) -> SearchResultsPage:
    try:
        record = await svc.get_search(db, search_id)
        rows, total = await svc.search_results(
            db,
            search_id,
            search_text=search,
            status=None if status_filter == "all" else status_filter,
            sort=sort,
            order=order,
            page=page,
            page_size=page_size,
        )
    except svc.NotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Search not found")

    duplicates = await svc.already_saved_ids(
        db, [r.id for r in rows], excluding_search=search_id
    )

    return SearchResultsPage(
        search=SearchResponse.model_validate(record),
        items=[TenderResponse.model_validate(r) for r in rows],
        already_saved=sorted(duplicates),
        total=total,
        page=page,
        page_size=page_size,
        pages=max(1, -(-total // page_size)),
    )
