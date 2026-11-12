"""Regressions for the "Broken outright" items of the 2026-11 code review:
features that failed every time they were used."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from tests.test_authz_boundaries import _make_engagement


# ── Admin: stats scope mode saved, then 500'd (its tail was stranded) ──

async def test_stats_scope_mode_put_returns_the_mode(client, make_user, authenticate_as):
    authenticate_as(await make_user(role="admin"))
    r = await client.put("/admin/settings/stats-scope-mode", json={"mode": "scoped"})
    assert r.status_code == 200, r.text
    assert r.json() == {"mode": "scoped"}
    assert (await client.get("/admin/settings/stats-scope-mode")).json()["mode"] == "scoped"


# ── Deleting a user: API tokens, and lists of what they created ──

async def test_user_with_api_token_can_be_deleted(client, db_session, make_user, authenticate_as):
    from sqlalchemy import select
    from models.api_token import ApiToken
    gone = await make_user()
    db_session.add(ApiToken(name="ci", token_hash=uuid.uuid4().hex * 2, token_prefix="rw_test",
                            permission="ro", user_id=gone.id))
    await db_session.flush()
    await db_session.refresh(gone, ["api_tokens"])  # loaded collection: the case the ORM used to null out

    authenticate_as(await make_user(role="admin"))
    assert (await client.delete(f"/admin/users/{gone.id}")).status_code == 204
    left = (await db_session.execute(select(ApiToken).where(ApiToken.user_id == gone.id))).scalars().all()
    assert left == []


async def test_lists_survive_their_creator_being_deleted(client, db_session, make_user, authenticate_as):
    from models.testcase import TestCase
    from models.testcase_template import TestCaseTemplate
    from models.vault import VaultItem
    eng = await _make_engagement(db_session)
    gone = await make_user()
    db_session.add_all([
        TestCase(id=str(uuid.uuid4()), engagement_id=eng.id, title="tc", category="Recon",
                 description="d", created_by=gone.id),
        VaultItem(id=str(uuid.uuid4()), engagement_id=eng.id, name="cred", item_type="password",
                  created_by=gone.id),
        TestCaseTemplate(id=str(uuid.uuid4()), title="tpl", category="Recon", description="d",
                         created_by=gone.id),
    ])
    await db_session.flush()

    authenticate_as(await make_user(role="admin"))
    assert (await client.delete(f"/admin/users/{gone.id}")).status_code == 204
    for url in (f"/testcases?engagement_id={eng.id}", f"/vault?engagement_id={eng.id}", "/testcase-templates"):
        r = await client.get(url)
        assert r.status_code == 200, (url, r.text)


# ── PDF attack graph with a filtered finding set ──

def _graph_self(findings, testcases, cleanup=()):
    return SimpleNamespace(
        findings=findings, testcases=testcases, cleanup_artifacts=list(cleanup),
        _display_ids=lambda: ({}, {}),
        _graph_status=lambda _t: "executed",
        _resolved_chain=lambda: ([], [], set()),
    )


def test_attack_graph_drops_edges_to_filtered_out_findings():
    from utils.report_generator import PDFReportGenerator as G
    kept = SimpleNamespace(id="f-kept", title="kept", severity="HIGH", assets=[])
    dropped = SimpleNamespace(id="f-dropped", title="filtered out", severity="LOW", assets=[])
    tc = SimpleNamespace(id="t1", title="tc", parent_id=None, findings=[kept, dropped])
    ca = SimpleNamespace(title="artifact", assets=[], findings=[dropped])
    nodes, edges = G._build_full_graph(_graph_self([kept], [tc], [ca]))
    ids = {n["id"] for n in nodes}
    assert all(e["s"] in ids and e["t"] in ids for e in edges)
    layer = G._layer_nodes(nodes, edges)  # raised KeyError before
    assert layer["f-kept"] > layer["t1"]
    # And layering alone tolerates a dangling edge.
    assert G._layer_nodes(nodes, edges + [{"s": "t1", "t": "nope", "kind": "discovered"}]) == layer


# ── Wordlist Bloom filter and NTLM ──

def test_bloom_is_built_with_headroom_and_reports_overflow(monkeypatch):
    from utils import hash_utils as hu
    assert hu.bloom_capacity_for(0) >= 1_000_000
    assert hu.bloom_capacity_for(14_000_000) > 14_000_000

    svc = hu.BloomFilterService()
    monkeypatch.setattr(hu.BloomFilterService, "_shared_sync", staticmethod(lambda: None))
    svc.install(hu.BloomFilter(capacity=1000), 0)
    svc.add_many([f"pw{i}" for i in range(900)])
    assert not svc.over_capacity()
    svc.add_many([f"more{i}" for i in range(200)])
    assert svc.over_capacity()
    # Legacy shared metadata without a capacity field: derived from bits.
    bf = hu.BloomFilter(capacity=50_000)
    assert abs(hu._capacity_from_bits(bf.bit_count) - 50_000) < 50


def test_ntlm_is_computed_without_openssl_md4():
    from utils import hash_utils as hu
    assert hu.compute_ntlm("password") == "8846f7eaee8fb117ad06bdd830b7586c"
    assert hu._md4(b"").hex() == "31d6cfe0d16ae931b73c59d7e0c089c0"
    assert hu._md4(b"abc").hex() == "a448017aaf21d8525fc10ae87aa6729d"
    assert hu._md4(b"1234567890" * 8).hex() == "e33b4ddc9c38f2199c3e7b164fcc0536"


async def test_ntlm_backfill_fills_empty_rows(db_engine, monkeypatch):
    """Rows committed outside the test transaction (db_session's commits
    aren't visible to the backfill's own connection)."""
    import asyncio
    import asyncpg
    from routers import wordlist as wl
    from tests.conftest import _test_db_url

    url = _test_db_url()
    conn = await asyncpg.connect(url.replace("postgresql+asyncpg://", "postgresql://", 1))
    meta_id = str(uuid.uuid4())
    try:
        await conn.execute("INSERT INTO wordlist_meta (id, filename, entry_count, status, created_at) VALUES ($1, 'legacy.txt', 2, 'READY', now())", meta_id)
        await conn.execute("INSERT INTO wordlist_entries (password, ntlm, md5, sha1, source) VALUES "
                           "('password', '', 'x', 'y', $1), ('Summer2024!', NULL, 'x', 'y', $1)", meta_id)
        monkeypatch.setenv("DATABASE_URL", url)
        filled = await asyncio.to_thread(wl.backfill_missing_ntlm_sync, 1)
        assert filled >= 2
        got = dict(await conn.fetch("SELECT password, ntlm FROM wordlist_entries WHERE source = $1", meta_id))
        assert got["password"] == "8846f7eaee8fb117ad06bdd830b7586c"
        assert len(got["Summer2024!"]) == 32
        assert await asyncio.to_thread(wl.backfill_missing_ntlm_sync) == 0  # nothing left: no-op
    finally:
        await conn.execute("DELETE FROM wordlist_entries WHERE source = $1", meta_id)
        await conn.execute("DELETE FROM wordlist_meta WHERE id = $1", meta_id)
        await conn.close()


# ── SAML: request-binding cookie must survive the IdP's cross-site POST ──

async def _saml_login_cookie(client, db_session, monkeypatch, base_url):
    import routers.auth as auth_router
    from models.auth_settings import AuthSetting
    db_session.add(AuthSetting(key="saml_enabled", value="true", is_encrypted=False))
    await db_session.flush()
    monkeypatch.setattr(auth_router, "build_saml_request_url",
                        lambda cfg, return_to: ("https://idp.example/sso?SAMLRequest=x", "ONELOGIN_req1"))
    r = await client.get(f"{base_url}/auth/saml/login", follow_redirects=False)
    assert r.status_code in (302, 307), r.text
    return r.headers["set-cookie"].lower()


async def test_saml_request_cookie_is_samesite_none_over_https(client, db_session, monkeypatch):
    cookie = await _saml_login_cookie(client, db_session, monkeypatch, "https://redwire.example")
    assert "saml_request_id=" in cookie and "samesite=none" in cookie and "secure" in cookie


async def test_saml_request_cookie_stays_lax_over_http(client, db_session, monkeypatch):
    cookie = await _saml_login_cookie(client, db_session, monkeypatch, "http://localhost")
    assert "samesite=lax" in cookie and "secure" not in cookie
