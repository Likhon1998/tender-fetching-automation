from datetime import datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Frequency = Literal["daily", "weekly", "biweekly", "monthly", "custom"]


class ScheduleGroupCreate(BaseModel):
    """The two wizard steps combined: chosen sites, then timing."""

    name: str | None = Field(default=None, max_length=80)
    site_ids: list[int] = Field(min_length=1)
    frequency: Frequency
    run_at: time = Field(description="Local wall-clock time, e.g. 08:30")
    interval_days: int | None = Field(default=None, ge=1, le=365)
    enabled: bool = True

    @model_validator(mode="after")
    def check_interval(self):
        if self.frequency == "custom" and not self.interval_days:
            raise ValueError("A custom schedule needs interval_days")
        return self


class ScheduleGroupUpdate(BaseModel):
    """Only send what changes."""

    name: str | None = Field(default=None, max_length=80)
    site_ids: list[int] | None = Field(default=None, min_length=1)
    frequency: Frequency | None = None
    run_at: time | None = None
    interval_days: int | None = Field(default=None, ge=1, le=365)
    enabled: bool | None = None


class ScheduledSite(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    active: bool


class ScheduleGroupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str | None
    frequency: Frequency
    interval_days: int | None
    run_at: time
    enabled: bool
    sites: list[ScheduledSite]
    next_run_at: datetime | None
    last_run_at: datetime | None
    last_status: str | None
    last_error: str | None
    created_at: datetime
    timezone: str


class SiteAvailability(BaseModel):
    """One row of the site picker. A site already in a group is not selectable."""

    site_id: int
    site_name: str
    site_url: str
    site_active: bool
    group_id: int | None
    group_name: str | None
