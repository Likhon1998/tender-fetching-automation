import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SearchStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


# The tenders a user chose to keep from a search.
#
# A search scrapes and shows everything it found; only the rows the user ticks
# end up here. Tenders are globally unique by title, so one found by an earlier
# search is not stored again, and without this table there would be no record
# of which search a saved tender belongs to.
search_tenders = Table(
    "search_tenders",
    Base.metadata,
    Column(
        "search_id",
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("searches.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "tender_id",
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("tenders.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Search(Base):
    """One run of the search wizard: chosen sites, chosen categories, results.

    A search scrapes the selected sites there and then, so it carries progress
    fields while it runs. It only becomes a saved list once the user picks
    which of the results to keep; until then `saved` stays false.

    Site and category selections are stored as both ids and names. The ids
    drive the query; the names are a snapshot so an old search still reads
    sensibly if something is renamed later.
    """

    __tablename__ = "searches"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_by_username: Mapped[str | None] = mapped_column(String(50), nullable=True)

    site_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)
    site_names: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    category_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)
    category_names: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    # Notices the classifier could not place are hidden unless asked for.
    include_uncategorised: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    status: Mapped[str] = mapped_column(
        String(20), nullable=False,
        default=SearchStatus.PENDING.value, server_default=SearchStatus.PENDING.value,
    )

    # Progress while the scrape runs, polled by the wizard.
    sites_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    sites_done: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    current_site: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # False until the user saves a selection from the results.
    saved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    saved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tender_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<Search {self.id} [{self.status}] {self.tender_count} tenders>"
