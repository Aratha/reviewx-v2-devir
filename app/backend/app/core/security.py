"""Password hashing and signed JWT access-token primitives."""

import secrets
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any
from uuid import UUID

import jwt
from jwt import InvalidTokenError
from pwdlib import PasswordHash
from pydantic import BaseModel, Field, ValidationError

from app.core.config import get_settings

_password_hash = PasswordHash.recommended()
# rules/58: the baseline login is password-only, so NIST SP 800-63-4 requires at least 15
# characters, accepts at least 64, and forbids composition rules. The upper bound only caps the
# hashing work of one request.
PASSWORD_MIN_LENGTH = 15
PASSWORD_MAX_LENGTH = 128
# rules/58 blocklist: widely used passwords long enough to pass the length rule. An organization
# breached-password service can extend it; this list is only the offline baseline.
_COMMON_PASSWORDS = frozenset(
    {
        "123456789012345",
        "1234567890123456",
        "administrator123",
        "changemechangeme",
        "iloveyouiloveyou",
        "letmeinletmein123",
        "passwordpassword",
        "password12345678",
        "qwertyuiopasdfgh",
        "qwertyuiopasdfghjkl",
        "welcome123456789",
    }
)


class TokenClaims(BaseModel):
    """Claims trusted by request middleware after signature and audience validation."""

    sub: UUID
    username: str
    tenant_id: UUID
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    is_super_admin: bool = False
    exp: int
    iat: int
    iss: str
    aud: str


def validate_password_strength(password: str, *, context: Iterable[str] = ()) -> None:
    """Apply the baseline bootstrap/password-creation policy.

    Length counts Unicode characters of the password exactly as entered; spaces and non-ASCII
    characters are kept and no character-class composition is required. ``context`` carries the
    account's own identifiers, such as the username, which the password must not contain.
    """

    if len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"password must contain at least {PASSWORD_MIN_LENGTH} characters")
    if len(password) > PASSWORD_MAX_LENGTH:
        raise ValueError(f"password must contain at most {PASSWORD_MAX_LENGTH} characters")
    folded = password.casefold()
    if folded in _COMMON_PASSWORDS or _repeats_a_short_unit(folded):
        raise ValueError("password is too common")
    if any(len(word) >= 4 and word.casefold() in folded for word in context):
        raise ValueError("password must not contain the account name")


def _repeats_a_short_unit(value: str) -> bool:
    """Detect passwords such as ``aaaa...`` or ``abcabc...`` built from one short repeated unit."""

    return any(
        len(value) % size == 0 and value == value[:size] * (len(value) // size)
        for size in range(1, 5)
    )


def hash_password(password: str, *, context: Iterable[str] = ()) -> str:
    validate_password_strength(password, context=context)
    return _password_hash.hash(password)


@lru_cache(maxsize=1)
def _unknown_account_hash() -> str:
    return _password_hash.hash(secrets.token_urlsafe(32))


def verify_password(password: str, password_hash: str | None) -> bool:
    """Verify a password; a missing account still spends one hash verification.

    Equal work keeps login response time from revealing whether a username exists.
    """

    try:
        verified = _password_hash.verify(password, password_hash or _unknown_account_hash())
    except (ValueError, TypeError):
        return False
    return verified and password_hash is not None


def create_access_token(
    *,
    subject: UUID,
    username: str,
    tenant_id: UUID,
    roles: list[str],
    permissions: list[str],
    is_super_admin: bool,
) -> str:
    """Create a short-lived access token."""

    settings = get_settings()
    now = datetime.now(UTC)
    expires_delta = timedelta(minutes=settings.access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "username": username,
        "tenant_id": str(tenant_id),
        "roles": sorted(set(roles)),
        "permissions": sorted(set(permissions)),
        "is_super_admin": is_super_admin,
        "iat": now,
        "exp": now + expires_delta,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }
    return jwt.encode(payload, settings.jwt_signing_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> TokenClaims:
    """Verify a token completely before exposing claims to authorization code."""

    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_verification_key,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["sub", "exp", "iat", "iss", "aud"]},
        )
        return TokenClaims.model_validate(payload)
    except (InvalidTokenError, ValidationError) as exc:
        raise InvalidTokenError("invalid access token") from exc
