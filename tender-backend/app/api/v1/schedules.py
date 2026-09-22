"""Schedule groups: sets of sites scraped together on the same cadence."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.capabilities import MANAGE_SCHEDULES
from app.core.config import settings
from app.core.deps import CurrentUser, require_capability
from app.db.session import get_db
from app.models.schedule import ScheduleGroup
from app.schemas.schedule import (
    ScheduleGroupCreate,
    ScheduleGroupResponse,
    ScheduleGroupUpdate,
    SiteAvailability,
)
from app.services import schedule_service as svc

router = APIRouter(prefix="/schedules", tags=["schedules"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
CanManage = Depends(require_capability(MANAGE_SCHEDULES))


def _to_response(group: ScheduleGroup) -> ScheduleGroupResponse:
    return ScheduleGroupResponse(
        id=group.id,
        name=group.name,
        frequency=group.frequency,
        interval_days=group.interval_days,
        run_at=group.run_at,
        enabled=group.enabled,
        sites=sorted(
            ({"id": s.id, "name": s.name, "active": s.active} for s in group.sites),
            key=lambda s: s["name"],
        ),
        next_run_at=group.next_run_at,
        last_run_at=group.last_run_at,
        last_status=group.last_status,
        last_error=group.last_error,
        created_at=group.created_at,
        timezone=settings.TIMEZONE,
    )


@router.get(
    "/site-availability",
    response_model=list[SiteAvailability],
    summary="Every site, and which schedule already holds it",
)
async def site_availability(
    db: DbSession, current_user: CurrentUser
) -> list[SiteAvailability]:
    """Drives the site picker.

    A site already in a group is returned with that group named, so the
    interface can grey it out and explain why rather than failing on save.
    """
    return [SiteAvailability(**row) for row in await svc.site_availability(db)]


@router.get("", response_model=list[ScheduleGroupResponse], summary="All schedules")
async def list_groups(
    db: DbSession, current_user: CurrentUser
) -> list[ScheduleGroupResponse]:
    return [_to_response(g) for g in await svc.list_groups(db)]


@router.post(
    "",
    response_model=ScheduleGroupResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[CanManage],
    summary="Create a schedule for a set of sites",
)
async def create_group(payload: ScheduleGroupCreate, db: DbSession):
    """Times are wall-clock in the server's configured timezone, not UTC."""
    try:
        group = await svc.create_group(
            db,
            site_ids=payload.site_ids,
            frequency=payload.frequency,
            run_at=payload.run_at,
            name=payload.name,
            interval_days=payload.interval_days,
            enabled=payload.enabled,
        )
    except svc.SiteAlreadyScheduled as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"message": str(exc), "clashes": exc.clashes},
        )
    except svc.NotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    except svc.InvalidSchedule as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return _to_response(group)


@router.get("/{group_id}", response_model=ScheduleGroupResponse, summary="One schedule")
async def get_group(group_id: int, db: DbSession, current_user: CurrentUser):
    try:
        return _to_response(await svc.get_group(db, group_id))
    except svc.NotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Schedule not found")


@router.patch(
    "/{group_id}",
    response_model=ScheduleGroupResponse,
    dependencies=[CanManage],
    summary="Change a schedule",
)
async def update_group(group_id: int, payload: ScheduleGroupUpdate, db: DbSession):
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No fields to update")
    try:
        group = await svc.update_group(db, group_id, changes)
    except svc.SiteAlreadyScheduled as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"message": str(exc), "clashes": exc.clashes},
        )
    except svc.NotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    except svc.InvalidSchedule as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return _to_response(group)


@router.delete(
    "/{group_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[CanManage],
    summary="Delete a schedule",
)
async def delete_group(group_id: int, db: DbSession) -> Response:
    """The sites stay, and become available to another schedule."""
    try:
        await svc.delete_group(db, group_id)
    except svc.NotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Schedule not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
