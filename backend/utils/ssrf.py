"""Outbound-request SSRF guard.

The backend fetches user-supplied URLs in a few places (threat-intel feeds,
automation webhooks). Without validation those features can be turned into a
server-side request forgery primitive against docker-internal services
(minio/redis/the backend itself), cloud instance-metadata (169.254.169.254),
or the deployment LAN.

`validate_outbound_url` requires an http(s) scheme and resolves the host,
rejecting the request if any resolved address is non-public. It is called at
*fetch* time (not only create time) so DNS rebinding between when a URL is
stored and when it is fetched is also caught.
"""
import asyncio
import ipaddress
from urllib.parse import urlsplit

ALLOWED_SCHEMES = ("http", "https")


class OutboundURLError(ValueError):
    """Raised when a URL is not permitted for an outbound server-side request."""


def _addr_blocked(ip: ipaddress._BaseAddress) -> bool:
    # Unwrap IPv4-mapped IPv6 (e.g. ::ffff:169.254.169.254) before classifying.
    if ip.version == 6 and getattr(ip, "ipv4_mapped", None) is not None:
        ip = ip.ipv4_mapped
    return (
        ip.is_private or ip.is_loopback or ip.is_link_local
        or ip.is_reserved or ip.is_multicast or ip.is_unspecified
        or not ip.is_global  # catch-all for CGNAT / non-routable ranges
    )


def _check(raw_url: str) -> None:
    parts = urlsplit((raw_url or "").strip())
    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        raise OutboundURLError(
            f"scheme {parts.scheme!r} is not permitted (http/https only)"
        )
    host = parts.hostname
    if not host:
        raise OutboundURLError("URL has no host")

    try:
        addrs = [ipaddress.ip_address(host)]  # host is already a literal IP
    except ValueError:
        import socket
        port = parts.port or (443 if parts.scheme.lower() == "https" else 80)
        try:
            infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
        except socket.gaierror as e:
            raise OutboundURLError(f"could not resolve host {host!r}") from e
        addrs = [ipaddress.ip_address(info[4][0].split("%", 1)[0]) for info in infos]

    if not addrs:
        raise OutboundURLError(f"host {host!r} resolved to no addresses")
    for ip in addrs:
        if _addr_blocked(ip):
            raise OutboundURLError(
                f"host {host!r} resolves to non-public address {ip}"
            )


def validate_outbound_url_sync(raw_url: str) -> None:
    """Synchronous validator (for Pydantic field validators at create time).

    Raises OutboundURLError if the URL is not a safe public http(s) URL."""
    _check(raw_url)


async def validate_outbound_url(raw_url: str) -> None:
    """Async validator (for fetch-time checks). Runs DNS resolution off the
    event loop. Raises OutboundURLError if the URL is not permitted."""
    await asyncio.to_thread(_check, raw_url)
