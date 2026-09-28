"""A real-TCP fake LLM endpoint with its own test CA (sql-review 006-llm-connection tests).

It speaks just enough HTTP/1.1 over TLS for the adapter: each request is recorded (path,
headers, body) and answered by the scenario the test installs. The certificate authority and
server key are generated per test run and never written outside the pytest temporary directory.
"""

import asyncio
import datetime as dt
import ipaddress
import json
import ssl
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

HOST_NAME = "llm.test.internal"


@dataclass
class RecordedRequest:
    method: str
    path: str
    headers: dict[str, str]
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body)


Writer = asyncio.StreamWriter
Scenario = Callable[[RecordedRequest, Writer], Awaitable[None]]


def _name(common_name: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])


def _certificate_authority() -> tuple[ec.EllipticCurvePrivateKey, x509.Certificate]:
    key = ec.generate_private_key(ec.SECP256R1())
    now = dt.datetime.now(dt.UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(_name("Deneme Kök CA"))
        .issuer_name(_name("Deneme Kök CA"))
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )
    return key, certificate


@dataclass
class TestPki:
    ca_path: Path
    certificate_path: Path
    key_path: Path


def write_pki(directory: Path) -> TestPki:
    ca_key, ca = _certificate_authority()
    server_key = ec.generate_private_key(ec.SECP256R1())
    now = dt.datetime.now(dt.UTC)
    server = (
        x509.CertificateBuilder()
        .subject_name(_name(HOST_NAME))
        .issuer_name(ca.subject)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.DNSName(HOST_NAME), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
            ),
            critical=False,
        )
        .add_extension(x509.ExtendedKeyUsage([x509.OID_SERVER_AUTH]), critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    directory.mkdir(parents=True, exist_ok=True)
    pki = TestPki(directory / "ca.pem", directory / "server.pem", directory / "server.key")
    pki.ca_path.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    pki.certificate_path.write_bytes(server.public_bytes(serialization.Encoding.PEM))
    pki.key_path.write_bytes(
        server_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return pki


def http_response(
    status: int, body: bytes, *, content_type: str = "application/json", extra: str = ""
) -> bytes:
    reason = {200: "OK", 302: "Found", 500: "Internal Server Error"}.get(status, "Status")
    head = (
        f"HTTP/1.1 {status} {reason}\r\nContent-Type: {content_type}\r\n"
        f"Content-Length: {len(body)}\r\n{extra}Connection: close\r\n\r\n"
    )
    return head.encode("ascii") + body


def sse_head() -> bytes:
    return (
        b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n"
        b"Transfer-Encoding: chunked\r\nConnection: close\r\n\r\n"
    )


def chunk(data: bytes) -> bytes:
    return f"{len(data):x}\r\n".encode("ascii") + data + b"\r\n"


def sse_event(payload: object) -> bytes:
    return chunk(b"data: " + json.dumps(payload).encode("utf-8") + b"\n\n")


def openai_delta(text: str, completion_tokens: int | None = None) -> dict[str, Any]:
    event: dict[str, Any] = {"choices": [{"delta": {"content": text}}]}
    if completion_tokens is not None:
        event["usage"] = {"completion_tokens": completion_tokens, "prompt_tokens": 7}
    return event


@dataclass
class FakeLlmServer:
    pki: TestPki
    scenario: Scenario | None = None
    requests: list[RecordedRequest] = field(default_factory=list)
    connections: int = 0
    active: int = 0
    peak: int = 0
    port: int = 0
    _server: asyncio.Server | None = None

    async def start(self, *, certificate: TestPki | None = None) -> FakeLlmServer:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        pki = certificate or self.pki
        context.load_cert_chain(pki.certificate_path, pki.key_path)
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0, ssl=context)
        self.port = self._server.sockets[0].getsockname()[1]
        return self

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    def url(self, path: str = "/v1") -> str:
        return f"https://{HOST_NAME}:{self.port}{path}"

    async def _handle(self, reader: asyncio.StreamReader, writer: Writer) -> None:
        self.connections += 1
        try:
            request_line = await reader.readline()
            if not request_line:
                return
            method, path, _ = request_line.decode("latin-1").split(" ", 2)
            headers: dict[str, str] = {}
            while True:
                line = (await reader.readline()).decode("latin-1").rstrip("\r\n")
                if not line:
                    break
                name, _, value = line.partition(":")
                headers[name.strip().lower()] = value.strip()
            body = await reader.readexactly(int(headers.get("content-length", "0")))
            request = RecordedRequest(method, path, headers, body)
            self.requests.append(request)
            self.active += 1
            self.peak = max(self.peak, self.active)
            try:
                assert self.scenario is not None
                await self.scenario(request, writer)
            finally:
                self.active -= 1
        except ConnectionError, asyncio.IncompleteReadError, ssl.SSLError:
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError, ssl.SSLError:
                pass
