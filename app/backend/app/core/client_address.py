"""Client address for rate limits: X-Forwarded-For only from a trusted ingress controller.

application-foundation 001 Requirement 9: the header counts only on a request whose direct peer
is inside a configured ingress network; any other source is ignored.
"""

from collections.abc import Sequence
from ipaddress import IPv4Network, IPv6Network, ip_address


def resolve_client_address(
    peer: str | None,
    forwarded_for: str | None,
    trusted_networks: Sequence[IPv4Network | IPv6Network],
) -> str:
    peer_address = (peer or "").strip()
    if not forwarded_for or not _is_trusted(peer_address, trusted_networks):
        return peer_address
    # The nearest trusted proxy appends the address it saw last; walk back over trusted hops.
    for candidate in reversed([item.strip() for item in forwarded_for.split(",")]):
        try:
            address = ip_address(candidate)
        except ValueError:
            return peer_address
        if not any(address in network for network in trusted_networks):
            return str(address)
    return peer_address


def _is_trusted(value: str, networks: Sequence[IPv4Network | IPv6Network]) -> bool:
    try:
        address = ip_address(value)
    except ValueError:
        return False
    return any(address in network for network in networks)
