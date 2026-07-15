"""Outbound-request SSRF guard (`utils/ssrf.py`).

`validate_outbound_url` (async) and `validate_outbound_url_sync` both defer
to `_check`, which requires an http(s) scheme and rejects any host that
resolves to a non-public address. These tests pin:

  - scheme restriction (http/https only; case-insensitive)
  - loopback / private / link-local / cloud-metadata literal IPs blocked
  - IPv4-mapped IPv6 unwrapped before classification
  - a normal public literal IP allowed
  - DNS-name paths: localhost (→ loopback) blocked, unresolvable host raises
  - the async wrapper behaves identically to the sync one

Public-IP tests use literal IPs (8.8.8.8) so no network egress is needed;
name-resolution tests use `localhost` (always resolvable, always loopback)
and the reserved `.invalid` TLD (RFC 6761 — guaranteed non-resolvable).
"""

from __future__ import annotations

import pytest

from utils.ssrf import (
    OutboundURLError,
    validate_outbound_url,
    validate_outbound_url_sync,
)


# ── scheme restriction ───────────────────────────────────────────────


class TestScheme:
    @pytest.mark.parametrize("url", [
        "ftp://8.8.8.8/x",
        "file:///etc/passwd",
        "gopher://8.8.8.8",
        "javascript:alert(1)",
        "://8.8.8.8",          # empty scheme
        "8.8.8.8",             # no scheme at all → urlsplit scheme ""
    ])
    def test_non_http_schemes_rejected(self, url):
        with pytest.raises(OutboundURLError, match="scheme"):
            validate_outbound_url_sync(url)

    def test_empty_url_rejected(self):
        with pytest.raises(OutboundURLError, match="scheme"):
            validate_outbound_url_sync("")

    def test_none_url_rejected(self):
        with pytest.raises(OutboundURLError, match="scheme"):
            validate_outbound_url_sync(None)

    def test_scheme_is_case_insensitive(self):
        # Uppercase scheme on a public IP must pass.
        validate_outbound_url_sync("HTTP://8.8.8.8")
        validate_outbound_url_sync("HtTpS://8.8.8.8")


# ── host present ─────────────────────────────────────────────────────


class TestHostPresent:
    def test_no_host_rejected(self):
        with pytest.raises(OutboundURLError, match="no host"):
            validate_outbound_url_sync("http://")


# ── literal IPs: blocked ranges ──────────────────────────────────────


class TestBlockedLiteralIPs:
    @pytest.mark.parametrize("host", [
        "127.0.0.1",           # loopback
        "127.5.5.5",
        "[::1]",               # IPv6 loopback
        "10.0.0.1",            # private A
        "192.168.1.1",         # private C
        "172.16.0.1",          # private B
        "169.254.1.1",         # link-local
        "169.254.169.254",     # cloud instance metadata
        "0.0.0.0",             # unspecified
        "255.255.255.255",     # reserved/broadcast
        "224.0.0.1",           # multicast
        "100.64.0.1",          # CGNAT (not is_global)
    ])
    def test_blocked(self, host):
        with pytest.raises(OutboundURLError, match="non-public"):
            validate_outbound_url_sync(f"http://{host}/path")

    def test_ipv4_mapped_ipv6_metadata_blocked(self):
        # ::ffff:169.254.169.254 must be unwrapped to its v4 form and blocked.
        with pytest.raises(OutboundURLError, match="non-public"):
            validate_outbound_url_sync("http://[::ffff:169.254.169.254]/latest/meta-data")

    def test_ipv6_unique_local_blocked(self):
        with pytest.raises(OutboundURLError, match="non-public"):
            validate_outbound_url_sync("http://[fc00::1]/")

    def test_ipv6_link_local_blocked(self):
        with pytest.raises(OutboundURLError, match="non-public"):
            validate_outbound_url_sync("http://[fe80::1]/")


# ── literal IPs: allowed public ──────────────────────────────────────


class TestAllowedPublic:
    def test_public_ipv4_allowed(self):
        # Returns None (no raise) for a global-scope address.
        assert validate_outbound_url_sync("https://8.8.8.8/resolve") is None

    def test_public_ipv4_with_port_allowed(self):
        assert validate_outbound_url_sync("https://8.8.8.8:8443/x") is None

    def test_public_ipv6_allowed(self):
        assert validate_outbound_url_sync("https://[2001:4860:4860::8888]/") is None


# ── DNS-name paths ───────────────────────────────────────────────────


class TestNameResolution:
    def test_localhost_name_resolves_to_loopback_blocked(self):
        # Exercises the getaddrinfo branch: localhost → 127.0.0.1 / ::1.
        with pytest.raises(OutboundURLError, match="non-public"):
            validate_outbound_url_sync("http://localhost/admin")

    def test_unresolvable_host_raises(self):
        # .invalid is reserved as guaranteed-non-resolvable (RFC 6761).
        with pytest.raises(OutboundURLError, match="could not resolve"):
            validate_outbound_url_sync("http://no-such-host.invalid/")


# ── async wrapper parity ─────────────────────────────────────────────


class TestAsyncWrapper:
    async def test_async_allows_public(self):
        assert await validate_outbound_url("https://8.8.8.8/x") is None

    async def test_async_blocks_metadata(self):
        with pytest.raises(OutboundURLError, match="non-public"):
            await validate_outbound_url("http://169.254.169.254/latest/meta-data")

    async def test_async_blocks_loopback_name(self):
        with pytest.raises(OutboundURLError, match="non-public"):
            await validate_outbound_url("http://localhost/")

    async def test_async_rejects_bad_scheme(self):
        with pytest.raises(OutboundURLError, match="scheme"):
            await validate_outbound_url("ftp://8.8.8.8/")

    async def test_async_raises_outbound_url_error_type(self):
        # OutboundURLError is a ValueError subclass — callers may catch either.
        with pytest.raises(ValueError):
            await validate_outbound_url("http://127.0.0.1/")
