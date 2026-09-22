from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class SiteCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    url: HttpUrl
    strategy: str | None = Field(default=None, max_length=60)
    active: bool = True

    @field_validator("name")
    @classmethod
    def tidy_name(cls, v: str) -> str:
        return " ".join(v.split())


class SiteUpdate(BaseModel):
    """All fields optional: this is a PATCH, only send what changes."""

    name: str | None = Field(default=None, min_length=2, max_length=120)
    url: HttpUrl | None = None
    strategy: str | None = Field(default=None, max_length=60)
    active: bool | None = None

    @field_validator("name")
    @classmethod
    def tidy_name(cls, v: str | None) -> str | None:
        return " ".join(v.split()) if v is not None else None


class SiteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    url: str
    strategy: str | None
    active: bool
    last_scraped_at: datetime | None
    last_scrape_error: str | None
    created_at: datetime
