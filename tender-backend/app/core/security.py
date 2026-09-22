"""Password hashing and JWT creation / verification.

Nothing in here touches the database. It is pure crypto + token plumbing so it
can be unit tested on its own.
"""

import uuid
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import settings

_hasher = PasswordHasher()


# --------------------------------------------------------------------------
# Passwords
# --------------------------------------------------------------------------
def hash_password(plain_password: str) -> str:
    """Hash a plaintext password with Argon2id."""
    return _hasher.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Check a plaintext password against a stored hash. Never raises."""
    try:
        _hasher.verify(password_hash, plain_password)
        return True
    except (VerifyMismatchError, InvalidHashError, Exception):
        return False


def needs_rehash(password_hash: str) -> bool:
    """True if the hash was made with older/weaker parameters."""
    try:
        return _hasher.check_needs_rehash(password_hash)
    except Exception:
        return False


# --------------------------------------------------------------------------
# JWT
# --------------------------------------------------------------------------
class TokenError(Exception):
    """Raised when a token is missing, malformed, expired or tampered with."""


def create_access_token(
    *, user_id: uuid.UUID | str, expires_minutes: int | None = None
) -> tuple[str, int]:
    """Create a signed access token.

    Returns (token, expires_in_seconds).

    The token carries only the user id. Capabilities are read from the
    database on every request, so revoking a permission takes effect at once
    rather than when the token happens to expire.

    IMPORTANT: the JWT payload is signed, not encrypted. Anyone holding the
    token can read these claims. Never put secrets in here.
    """
    expires_minutes = expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=expires_minutes)

    payload = {
        "sub": str(user_id),      # subject: who the token is about
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "jti": str(uuid.uuid4()),  # unique token id, needed later for revocation
        "typ": "access",
    }
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return token, expires_minutes * 60


def decode_access_token(token: str) -> dict:
    """Verify signature + expiry and return the payload. Raises TokenError."""
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("Token is invalid") from exc

    if payload.get("typ") != "access":
        raise TokenError("Wrong token type")
    if not payload.get("sub"):
        raise TokenError("Token is missing a subject")
    return payload
