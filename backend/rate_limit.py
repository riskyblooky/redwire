"""
Rate limiter configuration.

Separated into its own module to avoid circular imports between main.py and routers.
"""
import os

from slowapi import Limiter


def _client_ip_for_rate_limit(request) -> str:
    """Pick the bucket key for slowapi.

    Reads X-Real-IP — which the nginx config explicitly sets to the actual
    TCP peer (``proxy_set_header X-Real-IP $remote_addr``), overriding any
    value the client supplies — instead of slowapi's default
    ``get_remote_address``. The default returns ``request.client.host``,
    which, with uvicorn's ``--proxy-headers`` middleware enabled, is the
    *left-most* ``X-Forwarded-For`` token. A client rotating that header
    lands in a fresh bucket on every request and bypasses the
    ``5/minute`` throttle on ``/auth/login`` and friends.

    The fallback is a constant string — not ``request.client.host``. If a
    deployment is ever exposed without nginx in front,
    ``request.client.host`` is itself the attacker-controlled
    ``X-Forwarded-For`` value, so falling back to it would silently
    re-introduce the bypass. A constant fails closed: every client
    without a trusted proxy in front shares one bucket, which is noisy
    but safe. GHSA-xg53-8wgq-w9cw.
    """
    return request.headers.get("X-Real-IP") or "no-trusted-proxy"


def _storage_uri() -> str:
    """Counters live in Redis so every backend worker shares one budget per
    client (in-memory storage gives each worker its own, multiplying the
    allowed rate by the worker count). RATE_LIMIT_STORAGE_URI overrides;
    the test suite sets it to memory://."""
    return os.getenv("RATE_LIMIT_STORAGE_URI") or os.getenv("REDIS_URL") or "memory://"


# in_memory_fallback_enabled: if Redis goes away, limits keep applying per
# worker instead of failing requests or switching limiting off.
limiter = Limiter(
    key_func=_client_ip_for_rate_limit,
    storage_uri=_storage_uri(),
    in_memory_fallback_enabled=True,
    key_prefix="rw:rl",
)
