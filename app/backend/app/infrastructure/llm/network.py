"""Private-network policy for LLM traffic (sql-review/PRDs/006-llm-connection Requirement 4).

Every address a host name resolves to, and the address a connection actually reaches, must be
inside the organization's private ranges. The check runs in the connection layer before TLS or
any request byte, so a denied call never sends its body. There is no switch, setting or API that
lifts the policy.
"""

import asyncio
import socket
import ssl
from collections.abc import Awaitable, Callable, Iterable
from ipaddress import IPv4Address, IPv6Address, ip_address, ip_network
from typing import Any

import httpcore
import httpx

PRIVATE_NETWORKS = tuple(
    ip_network(network)
    for network in (
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "100.64.0.0/10",
        "::1/128",
        "fe80::/10",
        "fc00::/7",
    )
)

# (host, port) -> resolved IP address strings in resolver order.
Resolver = Callable[[str, int], Awaitable[list[str]]]


class NetworkPolicyDenied(Exception):
    """The endpoint resolves to, or connected to, an address outside the private ranges."""


class HostUnresolved(Exception):
    """The endpoint host name has no address."""


def is_private_address(value: str) -> bool:
    try:
        address: IPv4Address | IPv6Address = ip_address(value.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(address, IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return any(
        address.version == network.version and address in network for network in PRIVATE_NETWORKS
    )


async def system_resolver(host: str, port: int) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    addresses: list[str] = []
    for info in infos:
        address = str(info[4][0])
        if address not in addresses:
            addresses.append(address)
    return addresses


def _literal_address(host: str) -> str | None:
    try:
        return str(ip_address(host.strip("[]")))
    except ValueError:
        return None


async def resolve_private(
    resolver: Resolver, host: str, port: int, *, timeout: float | None
) -> list[str]:
    """Resolve ``host`` and require every address to be private; return them in order."""

    literal = _literal_address(host)
    if literal is not None:
        if not is_private_address(literal):
            raise NetworkPolicyDenied()
        return [literal]
    try:
        async with asyncio.timeout(timeout):
            addresses = await resolver(host, port)
    except TimeoutError:
        raise httpcore.ConnectTimeout("name resolution timed out") from None
    except OSError:
        raise HostUnresolved() from None
    if not addresses:
        raise HostUnresolved()
    if not all(is_private_address(address) for address in addresses):
        raise NetworkPolicyDenied()
    return addresses


class PrivateNetworkBackend(httpcore.AsyncNetworkBackend):
    """Resolve with the policy, connect to a checked address and verify the connected peer."""

    def __init__(
        self, resolver: Resolver, inner: httpcore.AsyncNetworkBackend | None = None
    ) -> None:
        self._resolver = resolver
        self._inner = inner or httpcore.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        addresses = await resolve_private(self._resolver, host, port, timeout=timeout)
        last_error: Exception | None = None
        for address in addresses:
            try:
                stream = await self._inner.connect_tcp(
                    address,
                    port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as error:
                last_error = error
                continue
            peer = stream.get_extra_info("server_addr")
            if not peer or not is_private_address(str(peer[0])):
                await stream.aclose()
                raise NetworkPolicyDenied()
            return stream
        assert last_error is not None
        raise last_error

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        raise NetworkPolicyDenied()

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


class PolicyTransport(httpx.AsyncHTTPTransport):
    """httpx transport whose connection pool connects only through PrivateNetworkBackend."""

    def __init__(
        self,
        *,
        ssl_context: ssl.SSLContext,
        max_connections: int,
        network_backend: httpcore.AsyncNetworkBackend,
    ) -> None:
        super().__init__(verify=ssl_context, trust_env=False)
        # httpx 0.28 builds its pool without a network-backend hook; the replacement keeps the
        # same TLS context and limits and routes every connection through the policy backend.
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=ssl_context,
            max_connections=max_connections,
            max_keepalive_connections=max_connections,
            keepalive_expiry=5.0,
            http1=True,
            http2=False,
            network_backend=network_backend,
        )


def tls_context(ca_bundle: str) -> ssl.SSLContext:
    """Verified TLS: the configured bundle, otherwise the image's system trust store."""

    context = ssl.create_default_context(cafile=ca_bundle or None)
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return context
