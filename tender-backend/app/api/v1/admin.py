"""Maintenance tasks: reclassification and manual scrapes."""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.capabilities import RUN_ADMIN_TASKS
from app.core.deps import require_capability
from app.db.session import get_db
from app.services import classification_service, maintenance_service
from app.services.ingestion_service import run_ingestion

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_capability(RUN_ADMIN_TASKS))],
)

DbSession = Annotated[AsyncSession, Depends(get_db)]

# Typing the word out is deliberate friction: this cannot be undone, and a
# misplaced click should not be enough to wipe the collected data.
CONFIRMATION = "CLEAR"


class ClearRequest(BaseModel):
    scope: str = Field(pattern="^(lists|everything)$")
    confirm: str


@router.post("/reclassify", summary="Re-run classification over all stored tenders")
async def reclassify(db: DbSession) -> dict:
    """Apply the current keyword lists to every tender already in the database.

    Useful after editing category keywords: notices that previously matched
    nothing can be picked up without scraping the sites again.
    """
    return await classification_service.reclassify_all(db)


@router.post(
    "/ingest",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start a scrape of every active site",
)
async def ingest(background: BackgroundTasks, site_id: int | None = None) -> dict:
    """Kick off a scrape and return immediately.

    A full run takes minutes, far longer than an HTTP request should stay
    open, so the work happens in the background. Progress shows up on each
    site as `last_scraped_at` and `last_scrape_error`.
    """
    background.add_task(run_ingestion, site_ids=[site_id] if site_id else None)
    return {
        "status": "started",
        "scope": f"site {site_id}" if site_id else "all active sites",
        "note": "Check each site's last_scraped_at and last_scrape_error for progress.",
    }


@router.get("/clear", summary="What clearing would remove")
async def clear_preview(db: DbSession) -> dict:
    """Counts for the confirmation prompt, so the warning names real numbers."""
    return await maintenance_service.preview(db)


@router.post("/clear", summary="Delete saved lists, and optionally all tenders")
async def clear(payload: ClearRequest, db: DbSession) -> dict:
    """Reset the collected data.

    `lists` removes every saved list but keeps the tenders, so nothing needs
    scraping again. `everything` also removes the tenders. Users, sites and
    categories are never touched.
    """
    if payload.confirm != CONFIRMATION:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Type {CONFIRMATION} to confirm. This cannot be undone.",
        )
    return await maintenance_service.clear(db, payload.scope)
