"""Login-only LDAPS adapter: one bind with the user's own credentials, one read of their record.

application-foundation/PRDs/001-directory-login Decision 1-3 and Requirement 2: TLS always
verifies the CA bundle and the certificate host name, referrals are never followed, no service
account exists, and no other directory object is read. The password lives only in the
connection object for the duration of one call and is never logged.
"""

import asyncio
import contextlib
import socket
import ssl
from collections.abc import Callable, Iterator, Sequence
from typing import Any, Protocol
from uuid import UUID

from ldap3 import AUTO_BIND_NONE, NONE, SIMPLE, SUBTREE, Connection, Server, Tls
from ldap3.core.exceptions import LDAPException
from ldap3.utils.conv import escape_filter_chars

from app.domain.directory import (
    DirectoryAccount,
    DirectoryCredentialsRejected,
    DirectoryUnavailable,
    DirectoryUnavailableReason,
)

_RESULT_SUCCESS = 0
_RESULT_INVALID_CREDENTIALS = 49
# Active Directory reports the reason of a refused bind as "data <code>" in the diagnostic text;
# 533 means the account is disabled.
_DISABLED_ACCOUNT_DIAGNOSTIC = "data 533"

_ACCOUNT_DISABLE = 0x0002
_NORMAL_ACCOUNT = 0x0200
_TRUST_ACCOUNT_BITS = 0x0800 | 0x1000 | 0x2000
_NON_HUMAN_CLASSES = frozenset(
    {"computer", "msds-managedserviceaccount", "msds-groupmanagedserviceaccount"}
)
_ATTRIBUTES = (
    "objectGUID",
    "userPrincipalName",
    "displayName",
    "mail",
    "userAccountControl",
    "objectClass",
    "servicePrincipalName",
)
_LEGACY_CIPHERS = "DEFAULT:@SECLEVEL=1"
# ldap3 reports protocol failures as LDAPException; sockets and TLS fail as OSError (ssl.SSLError
# and socket timeouts are OSError subclasses).
_TRANSPORT_ERRORS = (LDAPException, OSError)


class LdapConnection(Protocol):
    """The part of ``ldap3.Connection`` this adapter uses."""

    result: dict[str, Any]
    response: list[dict[str, Any]] | None

    def open(self, read_server_info: bool = ...) -> Any: ...

    def bind(self) -> bool: ...

    def search(
        self,
        search_base: str,
        search_filter: str,
        search_scope: str = ...,
        attributes: Sequence[str] | None = ...,
        size_limit: int = ...,
    ) -> bool: ...

    def unbind(self) -> Any: ...


ConnectionFactory = Callable[[str, str], LdapConnection]


class LdapsLoginClient:
    """Authenticate one normalized UPN against Active Directory over verified LDAPS."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        base_dn: str,
        ca_bundle_path: str,
        connect_timeout_seconds: int,
        read_timeout_seconds: int,
        tls_legacy_compatibility: bool = False,
        connection_factory: ConnectionFactory | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._base_dn = base_dn
        self._ca_bundle_path = ca_bundle_path
        self._connect_timeout_seconds = connect_timeout_seconds
        self._read_timeout_seconds = read_timeout_seconds
        self._tls_legacy_compatibility = tls_legacy_compatibility
        self._connection_factory = connection_factory or self.open_connection

    async def authenticate(self, user_principal_name: str, password: str) -> DirectoryAccount:
        # ldap3 blocks; one worker call keeps the event loop free and has no detached task.
        return await asyncio.to_thread(self._authenticate_blocking, user_principal_name, password)

    def open_connection(self, user_principal_name: str, password: str) -> LdapConnection:
        """Build the unopened ldap3 connection with verified TLS and no referral chasing."""

        tls = Tls(
            validate=ssl.CERT_REQUIRED,
            ca_certs_file=self._ca_bundle_path,
            version=ssl.PROTOCOL_TLS_CLIENT,
            valid_names=[self._host],
            ciphers=_LEGACY_CIPHERS if self._tls_legacy_compatibility else None,
        )
        server = Server(
            self._host,
            port=self._port,
            use_ssl=True,
            tls=tls,
            get_info=NONE,
            connect_timeout=self._connect_timeout_seconds,
        )
        connection: LdapConnection = Connection(
            server,
            user=user_principal_name,
            password=password,
            authentication=SIMPLE,
            auto_bind=AUTO_BIND_NONE,
            auto_referrals=False,
            auto_range=False,
            read_only=True,
            raise_exceptions=False,
            receive_timeout=self._read_timeout_seconds,
        )
        return connection

    def _authenticate_blocking(self, user_principal_name: str, password: str) -> DirectoryAccount:
        if not password:
            # An empty simple-bind password is an anonymous bind in LDAP; it is never sent.
            raise DirectoryCredentialsRejected()
        connection = self._connection_factory(user_principal_name, password)
        opened = False
        try:
            try:
                if connection.open(read_server_info=False) is False:
                    raise DirectoryUnavailable("transport")
                opened = True
                bound = connection.bind()
            except _TRANSPORT_ERRORS as exc:
                raise DirectoryUnavailable(_classify_failure(exc)) from None
            if not bound:
                _raise_for_refused_bind(connection.result)
            try:
                connection.search(
                    search_base=self._base_dn,
                    search_filter=(
                        f"(userPrincipalName={escape_filter_chars(user_principal_name)})"
                    ),
                    search_scope=SUBTREE,
                    attributes=list(_ATTRIBUTES),
                    size_limit=2,
                )
            except _TRANSPORT_ERRORS as exc:
                raise DirectoryUnavailable(_classify_failure(exc)) from None
            return _account_from_search(connection)
        finally:
            if opened:
                # Closing must not mask the authentication outcome.
                with contextlib.suppress(*_TRANSPORT_ERRORS):
                    connection.unbind()


def _raise_for_refused_bind(result: dict[str, Any]) -> None:
    if result.get("result") == _RESULT_INVALID_CREDENTIALS:
        diagnostic = str(result.get("message", "")).casefold()
        raise DirectoryCredentialsRejected(
            account_disabled=_DISABLED_ACCOUNT_DIAGNOSTIC in diagnostic
        )
    raise DirectoryUnavailable("transport")


def _account_from_search(connection: LdapConnection) -> DirectoryAccount:
    if connection.result.get("result") != _RESULT_SUCCESS:
        raise DirectoryUnavailable("incomplete")
    entries = [item for item in connection.response or () if item.get("type") == "searchResEntry"]
    if len(entries) != 1:
        raise DirectoryUnavailable("incomplete")
    raw = entries[0].get("raw_attributes") or {}
    guid_value = _single(raw, "objectGUID")
    upn = _text(raw, "userPrincipalName")
    uac_text = _text(raw, "userAccountControl")
    if guid_value is None or len(guid_value) != 16 or upn is None or uac_text is None:
        raise DirectoryUnavailable("incomplete")
    try:
        uac = int(uac_text)
    except ValueError:
        raise DirectoryUnavailable("incomplete") from None
    object_classes = {value.casefold() for value in _texts(raw, "objectClass")}
    is_human = (
        {"person", "user"} <= object_classes
        and not object_classes & _NON_HUMAN_CLASSES
        and bool(uac & _NORMAL_ACCOUNT)
        and not uac & _TRUST_ACCOUNT_BITS
        and not _texts(raw, "servicePrincipalName")
    )
    return DirectoryAccount(
        object_guid=UUID(bytes_le=guid_value),
        user_principal_name=upn.casefold(),
        display_name=_text(raw, "displayName"),
        mail=_text(raw, "mail"),
        enabled=not uac & _ACCOUNT_DISABLE,
        is_human=is_human,
    )


def _values(raw: dict[str, Any], name: str) -> list[bytes]:
    for key, value in raw.items():
        if key.casefold() == name.casefold():
            return [bytes(item) for item in value or () if isinstance(item, (bytes, bytearray))]
    return []


def _single(raw: dict[str, Any], name: str) -> bytes | None:
    values = _values(raw, name)
    return values[0] if len(values) == 1 else None


def _texts(raw: dict[str, Any], name: str) -> list[str]:
    result = []
    for value in _values(raw, name):
        try:
            decoded = value.decode("utf-8").strip()
        except UnicodeDecodeError:
            raise DirectoryUnavailable("incomplete") from None
        if decoded:
            result.append(decoded)
    return result


def _text(raw: dict[str, Any], name: str) -> str | None:
    values = _texts(raw, name)
    return values[0] if len(values) == 1 else None


def _exception_chain(exc: BaseException) -> Iterator[BaseException]:
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _classify_failure(exc: BaseException) -> DirectoryUnavailableReason:
    chain = list(_exception_chain(exc))
    described = " ".join(f"{type(item).__name__} {item}" for item in chain).casefold()
    if any(isinstance(item, (TimeoutError, socket.timeout)) for item in chain) or (
        "timed out" in described or "timeout" in described
    ):
        return "timeout"
    if any(isinstance(item, ssl.SSLError) for item in chain) or any(
        marker in described for marker in ("ssl", "certificate", "tls")
    ):
        return "tls"
    return "transport"
