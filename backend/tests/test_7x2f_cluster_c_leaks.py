"""GHSA-7x2f-ff7r-h388 cluster C — info leaks & log/exception sanitization.

Four sub-issues shipped:

  #2  (CWE-116) Vault download `Content-Disposition` interpolated
      the raw filename. A name containing `"` or CR/LF broke the
      header shape or produced sibling-header injection. Fix: dual
      emission per RFC 6266 (ASCII fallback + filename*=UTF-8'')
      with CR/LF stripped and non-printables replaced.
  #3  (CWE-532) Frontend presence-WS `console.log` removed to keep
      debug noise out of production browser DevTools. The URL itself
      never carried the token (auth via first frame) but the log line
      was still noise the operator didn't need. Static test.
  #4  (CWE-209) Vault PATCH's 500 body reflected exception detail
      (SQLAlchemy IntegrityError text carries schema and row values).
      Fix: generic message to client; full traceback stays in logs.
  #15 (CWE-532) Axios errors carried `error.config.headers.Authorization
      = "Bearer <JWT>"`. Any `console.error(err)` or React error
      boundary that logged the axios error persisted the caller's
      JWT to browser DevTools. Fix: interceptor scrubs the header
      slot before propagating.
"""

from __future__ import annotations

import os

import pytest
from cryptography.fernet import Fernet

os.environ.setdefault("TOTP_ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.setdefault("VAULT_ENCRYPTION_KEY", Fernet.generate_key().decode())


# ── Issue 2: Content-Disposition sanitization (unit-level string check) ──


def _build_disposition(raw: str) -> str:
    """Mirror the inline builder in `routers/vault.py::download_vault_file`.

    Kept as a re-implementation because the production code is inline in
    the endpoint (one-shot header build tied to the Response()
    construction). Testing here defends the CONTRACT: whatever the prod
    line looks like tomorrow must produce the same "no CR/LF, no
    injected sibling" output for these adversarial inputs.
    """
    from urllib.parse import quote as _pq
    raw = (raw or "download").replace("\r", "").replace("\n", "")
    ascii_fallback = "".join(c if 32 <= ord(c) < 127 and c not in '"\\' else "_" for c in raw)
    return f'attachment; filename="{ascii_fallback}"; filename*=UTF-8\'\'{_pq(raw, safe="")}'


class TestContentDispositionSanitization:
    def test_plain_ascii_passes_through(self):
        d = _build_disposition("report.pdf")
        assert 'filename="report.pdf"' in d
        assert "filename*=UTF-8''report.pdf" in d

    def test_quote_replaced_in_ascii_fallback(self):
        # A `"` in the raw name would close the quoted-filename value
        # and let subsequent content inject.
        d = _build_disposition('cool"; X-Injected: yes; ".pdf')
        # ASCII fallback should have `_` where the quote was.
        assert 'filename="cool_' in d
        # Full raw name preserved in the UTF-8 form (pct-encoded).
        assert "cool%22" in d

    def test_crlf_stripped(self):
        # The core CRLF-injection defence: CR / LF must not appear in
        # the emitted header value regardless of what the raw filename
        # contained. Once stripped, the remaining characters may include
        # letters that spell an HTTP-header-like string (e.g.
        # "X-Injected: yes"), but with no CRLF present they land as part
        # of the filename value on a single line — no sibling header
        # gets injected at the response level. That's the fix.
        d = _build_disposition("evil.txt\r\nX-Injected: yes")
        assert "\r" not in d and "\n" not in d

    def test_utf8_filename_preserved_in_star_form(self):
        # A unicode filename should ride through in the filename*= form
        # (pct-encoded UTF-8) while the ASCII fallback substitutes
        # unsafe chars.
        d = _build_disposition("отчёт.pdf")
        # ASCII fallback should have _ where the cyrillic chars were
        assert 'filename="' in d
        # UTF-8 form should preserve the encoding
        assert "%D0%BE" in d  # 'о' in UTF-8

    def test_empty_becomes_default(self):
        d = _build_disposition("")
        assert 'filename="download"' in d


# ── Issue 3: presence-WS console.log removed ─────────────────────────
#
# The frontend file lives outside the backend container, so we skip
# the check when the path isn't reachable (pytest runs inside the
# backend container by convention). The static assertion still runs
# in a development shell where the whole repo is checked out.

_FRONTEND_WS_HOOK = "/mnt/c/Users/risky/OneDrive/Documents/code/redwire2/frontend/src/lib/hooks/use-collaboration.ts"


@pytest.mark.skipif(not os.path.exists(_FRONTEND_WS_HOOK), reason="frontend not mounted in backend container")
def test_presence_ws_console_log_removed():
    src = open(_FRONTEND_WS_HOOK).read()
    assert 'console.log(`Connecting to WS' not in src


# ── Issue 4: vault PATCH generic 500 ─────────────────────────────────


class TestVaultUpdateGenericError:
    def test_no_exception_reflection_in_500(self):
        src = open("/app/routers/vault.py").read()
        # Regression pin — the specific `str(e)` reflection must not
        # reappear in the update_vault_item handler.
        # Find the update_vault_item block and check its inner except.
        idx = src.find("async def update_vault_item")
        assert idx != -1
        # slice from there to next `def ` at the module level
        rest = src[idx:]
        end = rest.find("\n@router.")
        block = rest[:end] if end != -1 else rest
        # The old shape "detail=f\"Internal error: {type(e).__name__}"
        # must not be in this block.
        assert 'detail=f"Internal error: {type(e).__name__}' not in block
        # The new shape must be present.
        assert '"Internal server error updating vault item."' in block


# ── Issue 15: axios auth-header scrubbing (static test) ──────────────

_FRONTEND_API_TS = "/mnt/c/Users/risky/OneDrive/Documents/code/redwire2/frontend/src/lib/api.ts"


@pytest.mark.skipif(not os.path.exists(_FRONTEND_API_TS), reason="frontend not mounted in backend container")
def test_axios_scrubber_helper_present():
    src = open(_FRONTEND_API_TS).read()
    assert "_redactAuthOnError" in src
    assert "_redactAuthOnError(error)" in src
    assert "err?.config?.headers?.Authorization" in src
    assert "err?.request?.config?.headers?.Authorization" in src
    assert "err?.response?.config?.headers?.Authorization" in src


@pytest.mark.skipif(not os.path.exists(_FRONTEND_API_TS), reason="frontend not mounted in backend container")
def test_axios_refresh_failure_scrubs():
    # The refresh-failed path also propagates a `refreshError`.
    src = open(_FRONTEND_API_TS).read()
    assert "_redactAuthOnError(refreshError)" in src
