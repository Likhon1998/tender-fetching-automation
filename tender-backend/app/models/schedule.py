import enum
from datetime import datetime, time

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    Time,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Frequency(str, enum.Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"
    CUSTOM = "custom"


# How many days each frequency waits. Monthly is absent on purpose: it means
# the same day of the following month, which is not a fixed number of days.
INTERVAL_DAYS = {
    Frequency.DAILY: 1,
    Frequency.WEEKLY: 7,
    Frequency.BIWEEKLY: 14,
}


# Which sites belong to which schedule group.
#
# site_id is unique across the whole table, not just within a group: a site in
# two groups would be scraped twice on overlapping days, and there would be no
# sensible answer to "when is this site next fetched". The interface greys out
# sites that are already spoken for rather than letting the insert fail.
schedule_group_sites = Table(
    "schedule_group_sites",
    Base.metadata,
    Column(
        "group_id",
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("schedule_groups.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "site_id",
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("sites.id", ondelete="CASCADE"),
        primary_key=True,
        unique=True,
    ),
)


class ScheduleGroup(Base):
    """A set of sites scraped together on the same cadence.

    Grouping rather than scheduling each site separately means one change
    covers a dozen sites, and the runner makes one pass instead of a dozen.

    `run_at` is a wall-clock time in the configured timezone, not UTC. People
    think in local time, and a group set for 08:00 should stay at 08:00 when
    the clocks change. `next_run_at` is the resolved UTC instant, so the runner
    can compare it directly against now.
    """

    __tablename__ = "schedule_groups"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    name: Mapped[str | None] = mapped_column(String(80), nullable=True)

    frequency: Mapped[str] = mapped_column(String(20), nullable=False)
    # Only used when frequency is "custom".
    interval_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    run_at: Mapped[time] = mapped_column(Time, nullable=False)

    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    # The next UTC instant this should fire. Also acts as the claim: a runner
    # moves it forward before scraping, so a second process finds nothing due.
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )

    sites = relationship("Site", secondary=schedule_group_sites, lazy="selectin")

    def __repr__(self) -> str:
        return f"<ScheduleGroup {self.name or self.id} {self.frequency} at {self.run_at}>"
