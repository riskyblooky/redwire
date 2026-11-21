"""GHSA-7x2f-ff7r-h388 cluster C — info leaks & log/exception sanitization.

Four sub-issues shipped:

  #2  (CWE-116) Vault download `Content-Disposition` interpolated
      the raw filename. A name containing `"` or CR/LF broke the
      header shape or produced sibling-header injection. Fix: dual
      emission per RFC 6266 (ASCII fallback + filename*=UTF-8'')
      with CR/LF stripped and non-printables replaced.
  #3  (CWE-532) Frontend presence-WS `console.log` removed to keep
      debug noise out of production browser DevTools. Static test
      (the frontend has no JS test runner); runs wherever the repo's
      frontend/ is checked out next to backend/, as in CI.
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
import uuid

import pytest

from tests.test_authz_boundaries import _make_engagement

# Backend root, wherever the suite runs (/app in the container, backend/ in CI).
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FRONTEND = os.path.join(os.path.dirname(_BACKEND), "frontend")
_needs_frontend = pytest.mark.skipif(
    not os.path.isdir(os.path.join(_FRONTEND, "src")),
    reason="frontend/ not checked out next to backend/ (e.g. inside the backend container)",
)


# ── Issue 2: Content-Disposition sanitization ────────────────────────


class TestContentDispositionSanitization:
    """The shared builder every download endpoint uses."""

    @staticmethod
    def _cd(raw):
        from utils.uploads import content_disposition_attachment
        return content_disposition_attachment(raw)

    def test_plain_ascii_passes_through(self):
        d = self._cd("report.pdf")
        assert 'filename="report.pdf"' in d
        assert "filename*=UTF-8''report.pdf" in d

    def test_quote_replaced_in_ascii_fallback(self):
        d = self._cd('cool"; X-Injected: yes; ".pdf')
        assert 'filename="cool_' in d
        assert "cool%22" in d

    def test_crlf_stripped(self):
        d = self._cd("evil.txt\r\nX-Injected: yes")
        assert "\r" not in d and "\n" not in d

    def test_utf8_filename_preserved_in_star_form(self):
        d = self._cd("отчёт.pdf")
        assert 'filename="' in d
        assert "%D0%BE" in d  # 'о' in UTF-8

    def test_empty_becomes_default(self):
        assert 'filename="download"' in self._cd("")


async def _vault_item(db, **fields):
    from models.vault import VaultItem
    eng = await _make_engagement(db)
    item = VaultItem(id=str(uuid.uuid4()), engagement_id=eng.id, name="v", **fields)
    db.add(item)
    await db.flush()
    return item


async def test_vault_download_header_is_sanitised(client, db_session, make_user, authenticate_as, monkeypatch):
    from routers import vault
    from utils.storage import storage_service

    async def _download(name):
        return b"payload"
    monkeypatch.setattr(storage_service, "download_file", _download)
    monkeypatch.setattr(vault, "should_log_vault_access", lambda *a: False)

    admin = await make_user(role="admin")
    item = await _vault_item(db_session, item_type="FILE", file_path="vault/x",
                             filename='evil".txt\r\nX-Injected: yes')
    authenticate_as(admin)

    r = await client.get(f"/vault/download/{item.id}")

    assert r.status_code == 200, r.text
    assert r.content == b"payload"
    assert "x-injected" not in r.headers
    cd = r.headers["content-disposition"]
    assert cd.startswith('attachment; filename="evil_.txtX-Injected: yes"')


# ── Issue 3: presence-WS console.log removed ─────────────────────────


@_needs_frontend
def test_presence_ws_console_log_removed():
    src = open(os.path.join(_FRONTEND, "src/lib/hooks/use-collaboration.ts")).read()
    assert "console.log(`Connecting to WS" not in src


# ── Issue 4: vault PATCH generic 500 ─────────────────────────────────


async def test_vault_update_500_does_not_reflect_the_exception(client, db_session, make_user, authenticate_as, monkeypatch):
    from routers import vault

    def _boom(*a, **k):
        raise RuntimeError('duplicate key value violates "vault_items_pkey" (password)=(hunter2)')
    monkeypatch.setattr(vault, "build_change_summary", _boom)

    admin = await make_user(role="admin")
    item = await _vault_item(db_session, item_type="CREDENTIAL", username="u", password="p")
    authenticate_as(admin)

    r = await client.patch(f"/vault/{item.id}", json={"name": "renamed"})

    assert r.status_code == 500
    assert r.json() == {"detail": "Internal server error updating vault item."}
    assert "hunter2" not in r.text and "RuntimeError" not in r.text


# ── Issue 15: axios auth-header scrubbing (static test) ──────────────


@_needs_frontend
def test_axios_scrubber_helper_present():
    src = open(os.path.join(_FRONTEND, "src/lib/api.ts")).read()
    assert "_redactAuthOnError(error)" in src
    assert "_redactAuthOnError(refreshError)" in src
    for slot in ("err?.config?.headers?.Authorization",
                 "err?.request?.config?.headers?.Authorization",
                 "err?.response?.config?.headers?.Authorization"):
        assert slot in src
