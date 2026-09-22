"""Reusable FastAPI dependencies for authentication and authorisation."""

import uuid
from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TokenError, decode_access_token
from app.db.session import get_db
from app.models.user import User, UserStatus
from app.services import user_service

bearer_scheme = HTTPBearer(auto_error=False)

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Validate the bearer token and load the user fresh from the database.

    We re-read the user every request rather than trusting the token's claims,
    so a disabled or demoted account loses access immediately instead of when
    their token happens to expire.
    """
    if credentials is None or not credentials.credentials:
        raise _UNAUTHORIZED

    try:
        payload = decode_access_token(credentials.credentials)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    try:
        user_id = uuid.UUID(payload["sub"])
    except (ValueError, KeyError, TypeError) as exc:
        raise _UNAUTHORIZED from exc

    user = await user_service.get_by_id(db, user_id)
    if user is None:
        raise _UNAUTHORIZED

    if user.status is not UserStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account is {user.status.value}",
        )

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_capability(*capabilities: str) -> Callable[..., Coroutine[Any, Any, User]]:
    """Dependency factory: restrict an endpoint to holders of a capability.

    Usage:
        @router.post("/sites", dependencies=[Depends(require_capability(MANAGE_SITES))])

    Holding any one of the listed capabilities is enough.
    """
    needed = set(capabilities)

    async def _checker(current_user: CurrentUser) -> User:
        if not needed & set(current_user.capabilities or []):
            readable = " or ".join(sorted(needed)).replace("_", " ")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action needs permission to {readable}.",
            )
        return current_user

    return _checker
