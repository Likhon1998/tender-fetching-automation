"""Account management, for holders of the manage_users capability.

There is no self-registration: the first admin comes from
`scripts/seed_admin.py`, and every other account is created here.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.capabilities import MANAGE_USERS
from app.core.deps import CurrentUser, require_capability
from app.core.security import hash_password
from app.db.session import get_db
from app.models.user import User, UserStatus
from app.schemas.user import (
    CapabilityInfo,
    UserCreate,
    UserResponse,
    UserUpdate,
    capability_catalogue,
)

router = APIRouter(prefix="/users", tags=["users"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
CanManageUsers = Depends(require_capability(MANAGE_USERS))


@router.get(
    "/capabilities",
    response_model=list[CapabilityInfo],
    summary="Every capability that can be granted",
)
async def list_capabilities(current_user: CurrentUser) -> list[CapabilityInfo]:
    """Readable by anyone signed in, so a user can see what the labels mean."""
    return capability_catalogue()


@router.get(
    "",
    response_model=list[UserResponse],
    dependencies=[CanManageUsers],
    summary="List all users",
)
async def list_users(db: DbSession) -> list[UserResponse]:
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return [UserResponse.model_validate(u) for u in result.scalars().all()]


async def _taken(db: AsyncSession, column, value: str, exclude=None) -> bool:
    stmt = select(User.id).where(func.lower(column) == value.strip().lower())
    if exclude is not None:
        stmt = stmt.where(User.id != exclude)
    return (await db.execute(stmt.limit(1))).scalar_one_or_none() is not None


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[CanManageUsers],
    summary="Create a user and set what they can do",
)
async def create_user(payload: UserCreate, db: DbSession) -> UserResponse:
    if await _taken(db, User.username, payload.username):
        raise HTTPException(status.HTTP_409_CONFLICT, "That username is already taken")
    if await _taken(db, User.email, payload.email):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "An account with that email already exists"
        )

    user = User(
        username=payload.username,
        full_name=payload.full_name,
        email=payload.email.strip().lower(),
        password_hash=hash_password(payload.password),
        capabilities=payload.capabilities,
        status=UserStatus.ACTIVE,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return UserResponse.model_validate(user)


async def _would_orphan_admin(
    db: AsyncSession, user: User, new_capabilities: list[str] | None, new_status
) -> bool:
    """True if this change would leave nobody able to manage users.

    Without this guard the last admin can remove their own permission or
    disable their own account and lock everyone out permanently, with no way
    back in short of editing the database by hand.

    The count is done in Python rather than with a JSON containment query,
    which is not portable across databases and fails quietly on some of them.
    """
    losing = (
        new_capabilities is not None and MANAGE_USERS not in new_capabilities
    ) or (new_status is not None and new_status is not UserStatus.ACTIVE)
    if not losing or not user.can(MANAGE_USERS):
        return False

    others = (await db.execute(select(User).where(User.id != user.id))).scalars().all()
    return not any(
        u.status is UserStatus.ACTIVE and u.can(MANAGE_USERS) for u in others
    )


@router.patch(
    "/{user_id}",
    response_model=UserResponse,
    dependencies=[CanManageUsers],
    summary="Change a user's details or capabilities",
)
async def update_user(
    user_id: uuid.UUID, payload: UserUpdate, db: DbSession
) -> UserResponse:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No fields to update")

    if "email" in changes and await _taken(db, User.email, changes["email"], user.id):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "An account with that email already exists"
        )

    if await _would_orphan_admin(
        db, user, changes.get("capabilities"), changes.get("status")
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This is the only account that can manage users. "
            "Give another account that permission first.",
        )

    if "password" in changes:
        user.password_hash = hash_password(changes.pop("password"))
    if "email" in changes:
        changes["email"] = changes["email"].strip().lower()

    for field, value in changes.items():
        setattr(user, field, value)

    await db.commit()
    await db.refresh(user)
    return UserResponse.model_validate(user)


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[CanManageUsers],
    summary="Delete a user",
)
async def delete_user(
    user_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> Response:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if user.id == current_user.id:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "You cannot delete your own account"
        )
    if await _would_orphan_admin(db, user, [], None):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This is the only account that can manage users.",
        )

    await db.delete(user)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
