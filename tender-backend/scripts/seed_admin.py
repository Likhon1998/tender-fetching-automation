"""Create (or update) the first admin account from environment variables.

This is the only way an account is created without another account doing it:
there is no self-registration, so this bootstraps the system. The admin holds
every capability and grants the rest to the users it creates.

Run with:  python -m scripts.seed_admin

Safe to run repeatedly: if the admin already exists it only resets the
password, it does not create a duplicate.
"""

import asyncio
import sys

from sqlalchemy import func, select

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.core.capabilities import ALL_CAPABILITIES
from app.models.user import User, UserStatus


async def main() -> int:
    if not settings.ADMIN_PASSWORD or len(settings.ADMIN_PASSWORD) < 12:
        print("ERROR: set ADMIN_PASSWORD in .env to at least 12 characters.")
        return 1

    async with AsyncSessionLocal() as db:
        stmt = select(User).where(
            func.lower(User.email) == settings.ADMIN_EMAIL.strip().lower()
        )
        existing = (await db.execute(stmt)).scalar_one_or_none()

        if existing:
            existing.password_hash = hash_password(settings.ADMIN_PASSWORD)
            existing.capabilities = list(ALL_CAPABILITIES)
            existing.status = UserStatus.ACTIVE
            await db.commit()
            print(f"Admin already existed. Password reset for {existing.email}")
            return 0

        admin = User(
            username=settings.ADMIN_USERNAME,
            full_name=settings.ADMIN_FULL_NAME,
            email=settings.ADMIN_EMAIL.strip().lower(),
            password_hash=hash_password(settings.ADMIN_PASSWORD),
            capabilities=list(ALL_CAPABILITIES),
            status=UserStatus.ACTIVE,
        )
        db.add(admin)
        await db.commit()
        print(f"Admin created: {admin.email}")
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
