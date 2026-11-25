"""SSRF protection: only allow URLs whose host resolves to public IP addresses.

Called when a target is registered and, later, before every check, because a
domain's DNS answer can change after registration (DNS rebinding).
"""

import ipaddress
import socket
from urllib.parse import urlsplit


class UnsafeURLError(ValueError):
    pass


def resolve_host(host: str, port: int) -> list[str]:
    """Return every IP address the host resolves to (IPv4 and IPv6)."""
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [info[4][0] for info in infos]


def is_public_ip(ip: str) -> bool:
    address = ipaddress.ip_address(ip)
    # Allowlist: only globally routable addresses pass. This rejects loopback,
    # private ranges, link-local (cloud metadata 169.254.169.254), carrier-grade
    # NAT, reserved ranges and IPv4-mapped IPv6 like ::ffff:127.0.0.1.
    # Multicast is reported as "global" by Python but is never a web server.
    return address.is_global and not address.is_multicast


def check_url_is_public(url: str) -> None:
    """Raise UnsafeURLError unless every IP of the URL's host is public."""
    parts = urlsplit(url)
    host = parts.hostname
    if not host:
        raise UnsafeURLError("URL has no host")
    port = parts.port or (443 if parts.scheme == "https" else 80)

    try:
        ips = resolve_host(host, port)
    except socket.gaierror:
        # If we cannot see where it points, we cannot prove it is safe.
        raise UnsafeURLError(f"Host {host!r} does not resolve") from None

    # Reject if ANY address is not public: the HTTP client might pick that one.
    for ip in ips:
        if not is_public_ip(ip):
            raise UnsafeURLError(f"Host {host!r} resolves to a non-public address")
