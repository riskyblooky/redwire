"""GHSA-7f5w-xj7p-cjj4 — source_url scheme validator regressions.

The Pydantic validator on ``IntelItemCreate.source_url`` and
``IntelItemUpdate.source_url`` refuses any scheme other than
``http://`` / ``https://``. Prior to this the field was
``Optional[str]`` with no scheme check, so an operator could store a
``javascript:`` URI that the finding-detail page rendered verbatim as
``<a href=...>`` — stored XSS on click. The frontend layers a defensive
scheme gate on top, but the backend validator is the load-bearing
control.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from schemas.intel import IntelItemCreate, IntelItemUpdate, _validate_source_url


# ── _validate_source_url: pure-logic contract ────────────────────────


class TestValidateSourceUrl:
    """The single validator both schemas share. Every attack shape the
    advisory named routes through here."""

    def test_none_passes(self):
        assert _validate_source_url(None) is None

    def test_empty_string_passes(self):
        # Empty is treated the same as unset — the field is Optional.
        assert _validate_source_url("") == ""

    def test_https_accepted(self):
        assert _validate_source_url("https://example.com/a") == "https://example.com/a"

    def test_http_accepted(self):
        assert _validate_source_url("http://example.com/a") == "http://example.com/a"

    def test_case_insensitive_scheme(self):
        # A `HTTPS://` value should still be accepted — the check is
        # case-insensitive so an over-eager URL cleaner elsewhere can't
        # accidentally reject legitimate mixed-case input.
        assert _validate_source_url("HTTPS://example.com") == "HTTPS://example.com"
        assert _validate_source_url("HtTp://example.com") == "HtTp://example.com"

    # The attacks the advisory named.

    def test_javascript_uri_rejected(self):
        with pytest.raises(ValueError, match="http:// or https://"):
            _validate_source_url("javascript:alert(1)")

    def test_data_uri_rejected(self):
        with pytest.raises(ValueError, match="http:// or https://"):
            _validate_source_url("data:text/html,<script>alert(1)</script>")

    def test_vbscript_rejected(self):
        with pytest.raises(ValueError):
            _validate_source_url("vbscript:msgbox('x')")

    def test_file_scheme_rejected(self):
        with pytest.raises(ValueError):
            _validate_source_url("file:///etc/passwd")

    def test_ftp_rejected(self):
        # Not an attack per se, but the frontend `<a href>` and
        # `window.open` sinks are for web content — restrict to what
        # they actually make sense for.
        with pytest.raises(ValueError):
            _validate_source_url("ftp://example.com/x")

    def test_leading_whitespace_javascript_rejected(self):
        # Some HTML parsers strip leading whitespace / control chars
        # from `href` values before evaluating the scheme. If we ever
        # relax the check to `.strip().startswith(...)`, this test
        # would still pass — but we deliberately don't, so a padded
        # payload can't sneak past by exploiting parser tolerance.
        with pytest.raises(ValueError):
            _validate_source_url("\tjavascript:alert(1)")

    def test_no_scheme_rejected(self):
        # A bare "example.com" is ambiguous — the frontend `<a>` would
        # treat it as a relative URL to a path under RedWire, which
        # isn't the field's intent. Refuse and let the operator fix.
        with pytest.raises(ValueError):
            _validate_source_url("example.com/threat-brief")


# ── Both schemas apply the validator (regression pin) ────────────────


class TestIntelItemCreateAppliesValidator:
    """A future refactor that dropped the `_v_source_url` binding on
    either schema would silently reintroduce the CVE. Pin both."""

    def test_create_rejects_javascript(self):
        with pytest.raises(ValidationError):
            IntelItemCreate(title="x", source_url="javascript:alert(1)")

    def test_create_accepts_https(self):
        item = IntelItemCreate(title="x", source_url="https://example.com/a")
        assert item.source_url == "https://example.com/a"

    def test_create_accepts_none(self):
        # The field is Optional — omitting it is legit.
        item = IntelItemCreate(title="x")
        assert item.source_url is None

    def test_update_rejects_javascript(self):
        with pytest.raises(ValidationError):
            IntelItemUpdate(source_url="javascript:alert(1)")

    def test_update_accepts_https(self):
        upd = IntelItemUpdate(source_url="https://example.com/a")
        assert upd.source_url == "https://example.com/a"

    def test_update_accepts_none(self):
        upd = IntelItemUpdate()
        assert upd.source_url is None
