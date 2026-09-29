import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserStatus(str, enum.Enum):
    ACTIVE = "active"
    PENDING = "pending"
    DISABLED = "disabled"


class User(Base):
    __tablename__ = "users"

    # Generated in Python so the id is known before flush. The migration also
    # sets a gen_random_uuid() default for rows inserted via raw SQL.
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    username: Mapped[str] = mapped_column(String(50), nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)

    # Never leaves the backend. Not exposed by any response schema.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # What this account may do. See app/core/capabilities.py. Stored as JSON
    # rather than a role column so an account can hold any combination.
    capabilities: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, name="user_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        server_default=UserStatus.ACTIVE.value,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def can(self, capability: str) -> bool:
        return capability in (self.capabilities or [])

    def __repr__(self) -> str:
        return f"<User {self.username} [{', '.join(self.capabilities or [])}]>"
