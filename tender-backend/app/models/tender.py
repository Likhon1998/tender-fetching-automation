# Aliased because this model has a column called `date`, which would
# otherwise shadow the type inside the class body.
from datetime import date as DateType
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# Triage states. The specification names only not_interested, so `new` is the
# implicit state everything else sits in until someone dismisses it.
STATUS_NEW = "new"
STATUS_NOT_INTERESTED = "not_interested"
STATUSES = (STATUS_NEW, STATUS_NOT_INTERESTED)


class Tender(Base):
    """A single tender notice scraped from a site.

    Every notice is stored, including ones the classifier could not place and
    ones older than the cutoff. Filtering happens at read time instead, so the
    relevance rules and date cutoff can change without re-scraping, and so we
    can measure how much the classifier is discarding.

    Site and category are held twice on purpose: a foreign key for reliable
    filtering and joins, and a text snapshot so a tender still shows where it
    came from even if the site is later renamed.
    """

    __tablename__ = "tenders"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )

    title: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)

    # Normalised ISO date, null when the source gave nothing parseable.
    date: Mapped[DateType | None] = mapped_column(Date, nullable=True)
    # Whatever the page actually said, always kept for auditing.
    date_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Whether `date` is when the notice was published or when bids are due.
    # Most sites publish the former; a few list the deadline instead.
    date_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="publish", server_default="publish"
    )

    # The deadline, where one could be found. Often stated inside the title
    # rather than in a column of its own.
    submission_date: Mapped[DateType | None] = mapped_column(Date, nullable=True)
    submission_date_raw: Mapped[str | None] = mapped_column(Text, nullable=True)

    pdf_link: Mapped[str | None] = mapped_column(Text, nullable=True)

    site_id: Mapped[int | None] = mapped_column(
        ForeignKey("sites.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    source_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Null means the classifier found no matching category.
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), nullable=True, index=True
    )
    category: Mapped[str | None] = mapped_column(String(120), nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)

    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=STATUS_NEW, server_default=STATUS_NEW
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )

    site = relationship("Site", lazy="noload")
    category_ref = relationship("Category", lazy="noload")

    def __repr__(self) -> str:
        return f"<Tender {self.title[:40]!r} [{self.status}]>"
