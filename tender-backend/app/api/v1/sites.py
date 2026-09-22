from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.capabilities import MANAGE_SITES
from app.core.deps import CurrentUser, require_capability
from app.db.session import get_db
from app.models.site import Site
from app.models.tender import Tender
from app.schemas.site import SiteCreate, SiteResponse, SiteUpdate
from app.services import reference_service as svc

router = APIRouter(prefix="/sites", tags=["sites"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
CanManage = Depends(require_capability(MANAGE_SITES))


@router.get("", response_model=list[SiteResponse], summary="List all sites")
async def list_sites(
    db: DbSession,
    current_user: CurrentUser,
    active_only: Annotated[bool, Query(description="Only return active sites")] = False,
) -> list[Site]:
    return await svc.list_all(db, Site, active_only=active_only)


@router.get("/{site_id}", response_model=SiteResponse, summary="Get a site")
async def get_site(site_id: int, db: DbSession, current_user: CurrentUser) -> Site:
    try:
        return await svc.get_one(db, Site, site_id)
    except svc.NotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Site not found")


@router.post(
    "",
    response_model=SiteResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[CanManage],
    summary="Create a site",
)
async def create_site(payload: SiteCreate, db: DbSession) -> Site:
    data = payload.model_dump()
    data["url"] = str(data["url"])  # HttpUrl -> str for the text column
    try:
        return await svc.create(db, Site, data)
    except svc.NameAlreadyExists:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "A site with that name already exists"
        )


@router.patch(
    "/{site_id}",
    response_model=SiteResponse,
    dependencies=[CanManage],
    summary="Update a site",
)
async def update_site(site_id: int, payload: SiteUpdate, db: DbSession) -> Site:
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No fields to update")
    if "url" in changes and changes["url"] is not None:
        changes["url"] = str(changes["url"])
    try:
        return await svc.update(db, Site, site_id, changes)
    except svc.NotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Site not found")
    except svc.NameAlreadyExists:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "A site with that name already exists"
        )


@router.delete(
    "/{site_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[CanManage],
    summary="Delete a site",
)
async def delete_site(site_id: int, db: DbSession) -> Response:
    """Hard delete. Once tenders reference sites, consider deactivating instead
    so historical tenders keep their source."""
    try:
        await svc.get_one(db, Site, site_id)
    except svc.NotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Site not found")

    # Refuse rather than cascade. Deleting a site that has tenders would
    # destroy their provenance, so an admin who wants to stop scraping a site
    # should pause it instead.
    referenced = (
        await db.execute(
            select(func.count()).select_from(Tender).where(Tender.site_id == site_id)
        )
    ).scalar_one()
    if referenced:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{referenced} tender(s) came from this site. Pause it instead of deleting it.",
        )

    await svc.delete(db, Site, site_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
