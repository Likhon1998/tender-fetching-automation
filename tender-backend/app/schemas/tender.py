# Aliased because these models have a field called `date`, which would
# otherwise shadow the type inside the class body.
from datetime import date as DateType
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.tender import STATUSES


class TenderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    date: DateType | None
    date_raw: str | None
    date_type: str
    submission_date: DateType | None
    submission_date_raw: str | None
    pdf_link: str | None
    site_id: int | None
    source_name: str | None
    source_url: str | None
    category_id: int | None
    category: str | None
    confidence: Decimal | None
    status: str
    created_at: datetime


class TenderPage(BaseModel):
    """A page of results plus the counts the UI needs to render pagination."""

    items: list[TenderResponse]
    total: int
    page: int
    page_size: int
    pages: int


class TenderStatusUpdate(BaseModel):
    """Triage. The only field a user may change on a tender."""

    status: Literal["new", "not_interested"]


class TenderCreate(BaseModel):
    """Used by the ingestion pipeline, not exposed to normal users."""

    title: str = Field(min_length=3)
    date: DateType | None = None
    date_raw: str | None = None
    pdf_link: str | None = None
    site_id: int | None = None
    source_name: str | None = None
    source_url: str | None = None
    category_id: int | None = None
    category: str | None = None
    confidence: Decimal | None = Field(default=None, ge=0, le=1)


assert set(TenderStatusUpdate.model_fields["status"].annotation.__args__) == set(STATUSES)
