from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _clean_keywords(values: list[str]) -> list[str]:
    """Trim, drop blanks, lowercase, and de-duplicate while keeping order."""
    seen: set[str] = set()
    cleaned: list[str] = []
    for raw in values:
        term = " ".join(raw.split()).lower()
        if term and term not in seen:
            seen.add(term)
            cleaned.append(term)
    return cleaned


class CategoryCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    keywords: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def tidy_name(cls, v: str) -> str:
        return " ".join(v.split())

    @field_validator("keywords")
    @classmethod
    def tidy_keywords(cls, v: list[str]) -> list[str]:
        return _clean_keywords(v)


class CategoryUpdate(BaseModel):
    """All fields optional: this is a PATCH, only send what changes."""

    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    keywords: list[str] | None = None

    @field_validator("name")
    @classmethod
    def tidy_name(cls, v: str | None) -> str | None:
        return " ".join(v.split()) if v is not None else None

    @field_validator("keywords")
    @classmethod
    def tidy_keywords(cls, v: list[str] | None) -> list[str] | None:
        return _clean_keywords(v) if v is not None else None


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    keywords: list[str]
    created_at: datetime
