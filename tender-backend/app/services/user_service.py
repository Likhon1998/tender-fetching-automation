"""All database logic for users. Routers call these; they never write SQL."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, needs_rehash, verify_password
from app.models.user import User


async def get_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await db.get(User, user_id)


async def get_by_identifier(db: AsyncSession, identifier: str) -> User | None:
    """Look up by username OR email, case-insensitively."""
    needle = identifier.strip().lower()
    stmt = select(User).where(
        or_(func.lower(User.username) == needle, func.lower(User.email) == needle)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _exists(db: AsyncSession, column, value: str) -> bool:
    stmt = select(User.id).where(func.lower(column) == value.strip().lower()).limit(1)
    return (await db.execute(stmt)).scalar_one_or_none() is not None


async def authenticate(db: AsyncSession, identifier: str, password: str) -> User | None:
    """Return the user on valid credentials, else None.

    Callers must give an identical error for every None, so we do not leak
    which usernames or emails exist.
    """
    user = await get_by_identifier(db, identifier)

    if user is None:
        # Burn roughly the same CPU as a real verify, so response timing does
        # not reveal whether the account exists.
        hash_password("dummy-password-for-timing-parity")
        return None

    if not verify_password(password, user.password_hash):
        return None

    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)

    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(user)
    return user
