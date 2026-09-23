import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.core.capabilities import ALL_CAPABILITIES, DESCRIPTIONS, clean
from app.models.user import UserStatus

USERNAME_PATTERN = r"^[A-Za-z0-9._-]+$"


def _password_rules(v: str) -> str:
    if v.strip() == "":
        raise ValueError("Password cannot be blank")
    return v


class UserCreate(BaseModel):
    """Body of POST /admin/users.

    Only someone holding manage_users can reach that endpoint, so capabilities
    are accepted here. There is no public registration route.
    """

    username: str = Field(min_length=3, max_length=50, pattern=USERNAME_PATTERN)
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)
    capabilities: list[str] = Field(default_factory=list)

    @field_validator("username")
    @classmethod
    def strip_username(cls, v: str) -> str:
        return v.strip()

    @field_validator("full_name")
    @classmethod
    def tidy_full_name(cls, v: str) -> str:
        return " ".join(v.split())

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        return _password_rules(v)

    @field_validator("capabilities")
    @classmethod
    def tidy_capabilities(cls, v: list[str]) -> list[str]:
        return clean(v)

    @model_validator(mode="after")
    def passwords_match(self):
        if self.password != self.confirm_password:
            raise ValueError("password and confirm_password do not match")
        return self


class UserUpdate(BaseModel):
    """Change an existing account. Only send what changes."""

    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    email: EmailStr | None = None
    capabilities: list[str] | None = None
    status: UserStatus | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)

    @field_validator("capabilities")
    @classmethod
    def tidy_capabilities(cls, v: list[str] | None) -> list[str] | None:
        return clean(v) if v is not None else None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str | None) -> str | None:
        return _password_rules(v) if v is not None else None


class PasswordChange(BaseModel):
    """A user changing their own password."""

    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        return _password_rules(v)

    @model_validator(mode="after")
    def check(self):
        if self.new_password != self.confirm_password:
            raise ValueError("new_password and confirm_password do not match")
        if self.new_password == self.current_password:
            raise ValueError("The new password must differ from the current one")
        return self


class UserResponse(BaseModel):
    """What we send back about a user. No password hash, ever."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    full_name: str
    email: EmailStr
    capabilities: list[str]
    status: UserStatus
    created_at: datetime
    last_login_at: datetime | None = None


class CapabilityInfo(BaseModel):
    """One capability, for the toggles on the user form and the profile page."""

    key: str
    description: str


def capability_catalogue() -> list[CapabilityInfo]:
    return [
        CapabilityInfo(key=key, description=DESCRIPTIONS[key])
        for key in ALL_CAPABILITIES
    ]
