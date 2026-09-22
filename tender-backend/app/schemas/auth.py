from pydantic import BaseModel, Field

from app.schemas.user import UserResponse


class AuthenticateRequest(BaseModel):
    """Body of POST /api/v1/authenticate.

    `identifier` accepts either the username or the email address, so the
    frontend does not have to care which the user typed.
    """

    identifier: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until the access token expires
    user: UserResponse
