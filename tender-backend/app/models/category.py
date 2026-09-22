from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Category(Base):
    """One of the tender categories the firm cares about.

    `keywords` holds the terms used for keyword scoring during classification.
    It lives in the database rather than in code so the list can be changed by
    an admin without a redeploy.
    """

    __tablename__ = "categories"

    # BIGSERIAL on Postgres; plain autoincrementing integer on SQLite, which
    # does not autoincrement BIGINT columns. Lets the test suite run offline.
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # JSON rather than a PG array so the same model works on SQLite in tests.
    keywords: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<Category {self.name}>"
