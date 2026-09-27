"""LDAPS login adapter contract with a signature-constrained fake connection.

application-foundation 001 Decision 1-3 and Requirement 2. No real directory is contacted: the
fake records the exact ldap3 calls and replays ldap3-shaped results and raw attributes.
"""

import ssl
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from ldap3.core.exceptions import LDAPSocketOpenError, LDAPSocketReceiveError

from app.domain.directory import (
    DirectoryAccount,
    DirectoryCredentialsRejected,
    DirectoryUnavailable,
)
from app.infrastructure.directory.ldap_login_client import LdapsLoginClient

pytestmark = pytest.mark.unit

UPN = "ad.soyad@corp.example.test"
HUMAN_UAC = 0x0200


def _raw(
    *,
    guid: UUID | None,
    upn: str = UPN,
    uac: int = HUMAN_UAC,
    classes: Sequence[str] = ("top", "person", "organizationalPerson", "user"),
    spn: Sequence[str] = (),
    mail: str | None = "Ad.Soyad@corp.example.test",
    display_name: str | None = "Ad Soyad",
) -> dict[str, list[bytes]]:
    raw: dict[str, list[bytes]] = {
        "userPrincipalName": [upn.encode()],
        "userAccountControl": [str(uac).encode()],
        "objectClass": [value.encode() for value in classes],
        "servicePrincipalName": [value.encode() for value in spn],
        "mail": [mail.encode()] if mail else [],
        "displayName": [display_name.encode()] if display_name else [],
    }
    if guid is not None:
        raw["objectGUID"] = [guid.bytes_le]
    return raw


class FakeConnection:
    """Mirrors the ldap3.Connection methods the adapter calls, with their keyword names."""

    def __init__(
        self,
        *,
        open_error: Exception | None = None,
        bind_ok: bool = True,
        bind_result: dict[str, Any] | None = None,
        search_error: Exception | None = None,
        search_result: dict[str, Any] | None = None,
        entries: Sequence[dict[str, list[bytes]]] = (),
        referrals: int = 0,
    ) -> None:
        self._open_error = open_error
        self._bind_ok = bind_ok
        self._bind_result = bind_result or {"result": 0, "description": "success"}
        self._search_error = search_error
        self._search_result = search_result or {"result": 0, "description": "success"}
        self._entries = entries
        self._referrals = referrals
        self.result: dict[str, Any] = {}
        self.response: list[dict[str, Any]] | None = None
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def open(self, read_server_info: bool = True) -> None:
        self.calls.append(("open", {"read_server_info": read_server_info}))
        if self._open_error is not None:
            raise self._open_error

    def bind(self) -> bool:
        self.calls.append(("bind", {}))
        self.result = self._bind_result
        return self._bind_ok

    def search(
        self,
        search_base: str,
        search_filter: str,
        search_scope: str = "SUBTREE",
        attributes: Sequence[str] | None = None,
        size_limit: int = 0,
    ) -> bool:
        self.calls.append(
            (
                "search",
                {
                    "search_base": search_base,
                    "search_filter": search_filter,
                    "search_scope": search_scope,
                    "attributes": list(attributes or ()),
                    "size_limit": size_limit,
                },
            )
        )
        if self._search_error is not None:
            raise self._search_error
        self.result = self._search_result
        self.response = [
            {"type": "searchResEntry", "dn": "CN=x", "raw_attributes": raw} for raw in self._entries
        ] + [{"type": "searchResRef", "uri": ["ldaps://other"]}] * self._referrals
        return self._search_result["result"] == 0

    def unbind(self) -> None:
        self.calls.append(("unbind", {}))


def _client(connection: FakeConnection, received: list[tuple[str, str]]) -> LdapsLoginClient:
    def factory(upn: str, password: str) -> FakeConnection:
        received.append((upn, password))
        return connection

    return LdapsLoginClient(
        host="dc01.corp.example.test",
        port=636,
        base_dn="DC=corp,DC=example,DC=test",
        ca_bundle_path="/unused/in/this/test.crt",
        connect_timeout_seconds=5,
        read_timeout_seconds=10,
        connection_factory=factory,
    )


async def test_one_bind_and_one_self_read_return_the_account() -> None:
    guid = uuid4()
    connection = FakeConnection(entries=[_raw(guid=guid)], referrals=1)
    received: list[tuple[str, str]] = []

    account = await _client(connection, received).authenticate(UPN, "correct horse battery")

    assert account == DirectoryAccount(
        object_guid=guid,
        user_principal_name=UPN,
        display_name="Ad Soyad",
        mail="Ad.Soyad@corp.example.test",
        enabled=True,
        is_human=True,
    )
    assert received == [(UPN, "correct horse battery")]
    assert [name for name, _ in connection.calls] == ["open", "bind", "search", "unbind"]
    assert connection.calls[0][1] == {"read_server_info": False}
    search = connection.calls[2][1]
    assert search == {
        "search_base": "DC=corp,DC=example,DC=test",
        "search_filter": f"(userPrincipalName={UPN})",
        "search_scope": "SUBTREE",
        "attributes": [
            "objectGUID",
            "userPrincipalName",
            "displayName",
            "mail",
            "userAccountControl",
            "objectClass",
            "servicePrincipalName",
        ],
        "size_limit": 2,
    }


async def test_filter_values_are_escaped() -> None:
    upn = "a*)(objectclass=*@corp.example.test"
    connection = FakeConnection(entries=[_raw(guid=uuid4(), upn=upn)])
    await _client(connection, []).authenticate(upn, "secret-value-123")
    search_filter = connection.calls[2][1]["search_filter"]
    assert search_filter == "(userPrincipalName=a\\2a\\29\\28objectclass=\\2a@corp.example.test)"


async def test_empty_password_never_reaches_the_directory() -> None:
    received: list[tuple[str, str]] = []
    connection = FakeConnection()
    with pytest.raises(DirectoryCredentialsRejected):
        await _client(connection, received).authenticate(UPN, "")
    assert received == []
    assert connection.calls == []


@pytest.mark.parametrize(
    ("message", "disabled"),
    (
        ("80090308: LdapErr: DSID-0C09044E, comment: AcceptSecurityContext error, data 52e", False),
        ("80090308: LdapErr: DSID-0C09044E, comment: AcceptSecurityContext error, data 533", True),
    ),
)
async def test_refused_bind_is_rejected_and_the_connection_closed(
    message: str, disabled: bool
) -> None:
    connection = FakeConnection(
        bind_ok=False,
        bind_result={"result": 49, "description": "invalidCredentials", "message": message},
    )
    with pytest.raises(DirectoryCredentialsRejected) as error:
        await _client(connection, []).authenticate(UPN, "wrong-password-value")
    assert error.value.account_disabled is disabled
    assert [name for name, _ in connection.calls] == ["open", "bind", "unbind"]


async def test_bind_refused_for_another_reason_is_unavailable_not_success() -> None:
    connection = FakeConnection(
        bind_ok=False, bind_result={"result": 8, "description": "strongerAuthRequired"}
    )
    with pytest.raises(DirectoryUnavailable) as error:
        await _client(connection, []).authenticate(UPN, "some-password-value")
    assert error.value.reason == "transport"


@pytest.mark.parametrize(
    ("failure", "reason"),
    (
        (
            LDAPSocketOpenError(
                "socket ssl wrapping error: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify"
            ),
            "tls",
        ),
        (ssl.SSLCertVerificationError("hostname mismatch"), "tls"),
        (LDAPSocketOpenError("socket connection error while opening: timed out"), "timeout"),
        (LDAPSocketReceiveError("error receiving data: timed out"), "timeout"),
        (
            LDAPSocketOpenError("socket connection error: [Errno 111] Connection refused"),
            "transport",
        ),
    ),
)
async def test_transport_failures_are_classified_and_never_succeed(
    failure: Exception, reason: str
) -> None:
    connection = FakeConnection(open_error=failure)
    with pytest.raises(DirectoryUnavailable) as error:
        await _client(connection, []).authenticate(UPN, "some-password-value")
    assert error.value.reason == reason
    assert "unbind" not in [name for name, _ in connection.calls]


async def test_search_timeout_is_unavailable() -> None:
    connection = FakeConnection(search_error=LDAPSocketReceiveError("timed out"))
    with pytest.raises(DirectoryUnavailable) as error:
        await _client(connection, []).authenticate(UPN, "some-password-value")
    assert error.value.reason == "timeout"
    assert connection.calls[-1][0] == "unbind"


@pytest.mark.parametrize(
    "entries",
    (
        [],
        [_raw(guid=uuid4()), _raw(guid=uuid4())],
        [_raw(guid=None)],
        [{**_raw(guid=uuid4()), "userAccountControl": []}],
        [{**_raw(guid=uuid4()), "objectGUID": [b"short"]}],
    ),
)
async def test_missing_or_ambiguous_record_is_incomplete(
    entries: list[dict[str, list[bytes]]],
) -> None:
    connection = FakeConnection(entries=entries)
    with pytest.raises(DirectoryUnavailable) as error:
        await _client(connection, []).authenticate(UPN, "some-password-value")
    assert error.value.reason == "incomplete"


async def test_size_limit_exceeded_is_incomplete() -> None:
    connection = FakeConnection(
        search_result={"result": 4, "description": "sizeLimitExceeded"},
        entries=[_raw(guid=uuid4()), _raw(guid=uuid4())],
    )
    with pytest.raises(DirectoryUnavailable) as error:
        await _client(connection, []).authenticate(UPN, "some-password-value")
    assert error.value.reason == "incomplete"


@pytest.mark.parametrize(
    "raw",
    (
        _raw(guid=uuid4(), classes=("top", "person", "user", "computer"), uac=0x1000),
        _raw(guid=uuid4(), spn=("HTTP/app.corp.example.test",)),
        _raw(
            guid=uuid4(),
            classes=("top", "person", "user", "msDS-GroupManagedServiceAccount"),
        ),
        _raw(guid=uuid4(), uac=0x0100),
    ),
)
async def test_computer_and_service_accounts_are_not_human(raw: dict[str, list[bytes]]) -> None:
    account = await _client(FakeConnection(entries=[raw]), []).authenticate(
        UPN, "some-password-value"
    )
    assert account.is_human is False


async def test_disabled_account_is_reported() -> None:
    raw = _raw(guid=uuid4(), uac=HUMAN_UAC | 0x0002)
    account = await _client(FakeConnection(entries=[raw]), []).authenticate(
        UPN, "some-password-value"
    )
    assert account.enabled is False


def test_real_connection_verifies_ca_and_host_name_and_ignores_referrals(tmp_path: Path) -> None:
    bundle = tmp_path / "directory-ca.crt"
    bundle.write_text("-----BEGIN CERTIFICATE-----\n-----END CERTIFICATE-----\n")
    client = LdapsLoginClient(
        host="dc01.corp.example.test",
        port=636,
        base_dn="DC=corp,DC=example,DC=test",
        ca_bundle_path=str(bundle),
        connect_timeout_seconds=5,
        read_timeout_seconds=10,
    )
    connection: Any = client.open_connection(UPN, "never-sent-in-this-test")
    server = connection.server
    assert server.ssl is True
    assert server.port == 636
    assert server.host == "dc01.corp.example.test"
    assert server.connect_timeout == 5
    assert server.tls.validate == ssl.CERT_REQUIRED
    assert server.tls.valid_names == ["dc01.corp.example.test"]
    assert server.tls.ca_certs_file == str(bundle)
    assert server.tls.ciphers is None
    assert connection.auto_referrals is False
    assert connection.read_only is True
    assert connection.receive_timeout == 10
    assert connection.closed is True


def test_legacy_compatibility_lowers_only_the_cipher_level(tmp_path: Path) -> None:
    bundle = tmp_path / "directory-ca.crt"
    bundle.write_text("-----BEGIN CERTIFICATE-----\n-----END CERTIFICATE-----\n")
    client = LdapsLoginClient(
        host="dc01.corp.example.test",
        port=636,
        base_dn="DC=corp,DC=example,DC=test",
        ca_bundle_path=str(bundle),
        connect_timeout_seconds=5,
        read_timeout_seconds=10,
        tls_legacy_compatibility=True,
    )
    tls = client.open_connection(UPN, "never-sent-in-this-test").server.tls  # type: ignore[attr-defined]
    assert tls.ciphers == "DEFAULT:@SECLEVEL=1"
    assert tls.validate == ssl.CERT_REQUIRED
    assert tls.valid_names == ["dc01.corp.example.test"]
