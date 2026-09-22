from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser
from app.core.rate_limit import is_rate_limited, reset as reset_rate_limit
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.schemas.auth import AuthenticateRequest, TokenResponse
from app.schemas.user import PasswordChange, UserResponse
from app.services import user_service

router = APIRouter(tags=["auth"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.post(
    "/authenticate",
    response_model=TokenResponse,
    summary="Log in and receive an access token",
)
async def authenticate(
    payload: AuthenticateRequest, request: Request, db: DbSession
) -> TokenResponse:
    """Exchange credentials for a JWT access token."""
    client_ip = request.client.host if request.client else "unknown"
    if is_rate_limited(f"login:{client_ip}"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again later.",
        )

    user = await user_service.authenticate(db, payload.identifier, payload.password)
    if user is None:
        # Same message for "no such user" and "wrong password" on purpose.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if user.status.value != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account is {user.status.value}",
        )

    reset_rate_limit(f"login:{client_ip}")
    token, expires_in = create_access_token(user_id=user.id)

    return TokenResponse(
        access_token=token,
        expires_in=expires_in,
        user=UserResponse.model_validate(user),
    )


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Validate the current token and return the logged in user",
)
async def me(current_user: CurrentUser) -> UserResponse:
    """The frontend calls this on load to decide whether to show the dashboard."""
    return UserResponse.model_validate(current_user)


@router.post(
    "/change-password",
    response_model=UserResponse,
    summary="Change your own password",
)
async def change_password(
    payload: PasswordChange, db: DbSession, current_user: CurrentUser
) -> UserResponse:
    """Requires the current password, so a borrowed session cannot lock the
    real owner out of their account."""
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your current password is not correct",
        )

    current_user.password_hash = hash_password(payload.new_password)
    await db.commit()
    await db.refresh(current_user)
    return UserResponse.model_validate(current_user)
