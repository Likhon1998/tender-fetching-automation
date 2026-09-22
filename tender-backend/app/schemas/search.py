from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.tender import TenderResponse


class SearchCreate(BaseModel):
    """What the wizard submits after the site and category steps."""

    site_ids: list[int] = Field(min_length=1)
    category_ids: list[int] = Field(default_factory=list)
    include_uncategorised: bool = False


class SearchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_by_username: str | None
    site_ids: list[int]
    site_names: list[str]
    category_ids: list[int]
    category_names: list[str]
    include_uncategorised: bool
    status: str
    sites_total: int
    sites_done: int
    current_site: str | None
    saved: bool
    tender_count: int
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class SaveSelection(BaseModel):
    """Which of a search's results to keep."""

    tender_ids: list[int] = Field(default_factory=list)


class ListFromTenders(BaseModel):
    """Keep a hand-picked set of tenders from the review inbox."""

    tender_ids: list[int] = Field(min_length=1)
    # Optional: added to an existing list when given, a new one when not.
    search_id: int | None = None


class SearchResultsPage(BaseModel):
    search: SearchResponse
    items: list[TenderResponse]
    # Tenders on this page that are already kept in another saved list, so the
    # results screen can mark them and stop them being saved twice.
    already_saved: list[int] = Field(default_factory=list)
    total: int
    page: int
    page_size: int
    pages: int


SortField = Literal["date", "title", "confidence", "created_at"]
SortOrder = Literal["asc", "desc"]
