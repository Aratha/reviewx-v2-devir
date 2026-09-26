"""Directory login contract shared by the login service and its LDAPS adapter.

application-foundation/PRDs/001-directory-login Requirement 1 and 2: one normalized UPN, one
bind with the user's own credentials and one read of the user's own record.
"""

import unicodedata
from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

DIRECTORY_ACCOUNT_MAX_LENGTH = 120
UPN_MAX_LENGTH = 254

DirectoryUnavailableReason = Literal["tls", "transport", "timeout", "incomplete"]


class InvalidDirectoryName(ValueError):
    """The login name cannot be turned into the single accepted UPN."""


class DirectoryCredentialsRejected(Exception):
    """The directory refused the bind; the caller answers with a generic 401."""

    def __init__(self, *, account_disabled: bool = False) -> None:
        super().__init__("directory credentials rejected")
        self.account_disabled = account_disabled


class DirectoryUnavailable(Exception):
    """The directory could not give a complete verified answer; never treated as success."""

    def __init__(self, reason: DirectoryUnavailableReason) -> None:
        super().__init__(f"directory unavailable: {reason}")
        self.reason: DirectoryUnavailableReason = reason


@dataclass(frozen=True, slots=True)
class DirectoryAccount:
    """The authenticated user's own directory record, reduced to the facts the service uses."""

    object_guid: UUID
    user_principal_name: str
    display_name: str | None
    mail: str | None
    enabled: bool
    is_human: bool


class DirectoryLoginPort(Protocol):
    """Authenticate one normalized UPN with the user's own password."""

    async def authenticate(self, user_principal_name: str, password: str) -> DirectoryAccount:
        """Bind once and read the caller's own record.

        Raises DirectoryCredentialsRejected when the directory refuses the bind and
        DirectoryUnavailable when TLS, transport, time or record completeness fails.
        """
        ...


def normalize_login_name(value: str) -> str:
    """Return the NFKC, trimmed, case-folded login name used for lookups and rate limits."""

    return unicodedata.normalize("NFKC", value).strip().casefold()


def normalize_upn(value: str, upn_suffix: str) -> str:
    """Return exactly one UPN for ``ad.soyad`` or ``ad.soyad@<suffix>``; never a retry variant."""

    name = normalize_login_name(value)
    suffix = normalize_login_name(upn_suffix).lstrip("@")
    if (
        not name
        or not suffix
        or name.count("@") > 1
        or any(
            character.isspace() or unicodedata.category(character)[0] == "C" for character in name
        )
        or "\\" in name
        or "/" in name
    ):
        raise InvalidDirectoryName("invalid directory login name")
    account, _, supplied_suffix = name.partition("@")
    if supplied_suffix and supplied_suffix != suffix:
        raise InvalidDirectoryName("directory suffix mismatch")
    if not account or len(account) > DIRECTORY_ACCOUNT_MAX_LENGTH:
        raise InvalidDirectoryName("invalid directory account")
    upn = f"{account}@{suffix}"
    if len(upn) > UPN_MAX_LENGTH:
        raise InvalidDirectoryName("directory UPN is too long")
    return upn


def validate_local_account_name(name: str, upn_suffix: str) -> str:
    """Return the normalized local account name; it may never carry the directory UPN suffix.

    application-foundation 001 Requirement 3: a name that matches a local account is checked
    only against the local password, so a local name must never look like a directory UPN.
    """

    normalized = normalize_login_name(name)
    suffix = normalize_login_name(upn_suffix).lstrip("@")
    if (
        not normalized
        or len(normalized) > DIRECTORY_ACCOUNT_MAX_LENGTH
        or any(
            character.isspace() or unicodedata.category(character)[0] == "C"
            for character in normalized
        )
    ):
        raise InvalidDirectoryName("invalid local account name")
    if suffix and suffix in normalized:
        raise InvalidDirectoryName("a local account name cannot contain the directory UPN suffix")
    return normalized
