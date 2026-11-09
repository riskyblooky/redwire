"""Admin Security Center: security-event recording on auth/admin paths, the
admin-config audit middleware, nginx log ingestion, and the
/admin/security endpoints' permission gates."""

from __future__ import annotations

import json
import uuid
from datetime import datetime

import pytest
from sqlalchemy import select

from models.security_event import HttpLogCursor, HttpRequestLog, HttpTrafficHourly, SecurityEvent


async def _events(db, event_type=None):
    q = select(SecurityEvent).order_by(SecurityEvent.created_at)
    if event_type:
        q = q.where(SecurityEvent.event_type == event_type)
    return (await db.execute(q)).scalars().all()


# ── Recording ───────────────────────────────────────────────────────────────

async def test_failed_and_successful_login_recorded(client, make_user, security_events_on):
    db = security_events_on
    user = await make_user(password="Right-pass-123")
    headers = {"X-Real-IP": "203.0.113.9", "User-Agent": "pytest-agent"}
    r = await client.post("/auth/login", json={"username": user.username, "password": "nope"}, headers=headers)
    assert r.status_code == 401
    r = await client.post("/auth/login", json={"username": "ghost_user", "password": "nope"}, headers=headers)
    assert r.status_code == 401
    r = await client.post("/auth/login", json={"username": user.username, "password": "Right-pass-123"}, headers=headers)
    assert r.status_code == 200

    rows = await _events(db, "login")
    assert [(e.outcome, e.username) for e in rows] == [
        ("failure", user.username), ("failure", "ghost_user"), ("success", user.username)]
    assert rows[0].user_id == user.id and rows[0].details == {"known_user": True}
    assert rows[1].user_id is None and rows[1].details == {"known_user": False}
    assert rows[0].reason == "invalid_credentials"
    assert all(e.ip == "203.0.113.9" and e.user_agent == "pytest-agent" for e in rows)


async def test_inactive_account_login_recorded(client, make_user, security_events_on):
    user = await make_user(password="Right-pass-123", is_active=False)
    r = await client.post("/auth/login", json={"username": user.username, "password": "Right-pass-123"})
    assert r.status_code == 403
    (ev,) = await _events(security_events_on, "login")
    assert (ev.outcome, ev.reason, ev.user_id) == ("failure", "inactive_account", user.id)


def _request():
    from starlette.requests import Request
    return Request({"type": "http", "method": "PATCH", "path": "/", "headers": [], "client": ("192.0.2.5", 1)})


# Called directly: through the HTTP client, the shared test session leaves
# User.groups unloaded at response serialization (the app's own session
# doesn't), which has nothing to do with what's under test.
async def test_admin_user_update_records_changes(make_user, security_events_on, monkeypatch):
    import auth.jwt
    from routers.admin import update_user
    from schemas.user import UserUpdate
    monkeypatch.setattr(auth.jwt, "revoke_all_user_tokens", lambda _uid: True)
    admin = await make_user(role="admin")
    target = await make_user(role="operator")
    await update_user(target.id, UserUpdate(role="team_lead", is_active=False), _request(), admin, security_events_on)
    (ev,) = await _events(security_events_on, "user_updated")
    assert ev.user_id == target.id and ev.actor_id == admin.id
    assert ev.details["changes"] == {"role": {"old": "operator", "new": "team_lead"},
                                     "is_active": {"old": True, "new": False}}
    assert ev.details["sessions_revoked"] is True


async def test_no_op_user_update_records_nothing(make_user, security_events_on):
    from routers.admin import update_user
    from schemas.user import UserUpdate
    admin = await make_user(role="admin")
    target = await make_user(role="operator")
    await update_user(target.id, UserUpdate(role="operator"), _request(), admin, security_events_on)
    assert await _events(security_events_on, "user_updated") == []


async def test_config_write_audited_by_middleware(client, make_user, authenticate_as, security_events_on):
    admin = await make_user(role="admin")
    authenticate_as(admin)
    r = await client.post("/admin/permissions/groups", json={"name": f"g_{uuid.uuid4().hex[:6]}"})
    assert r.status_code == 201, r.text
    r = await client.get("/admin/permissions/groups")  # reads aren't audited
    assert r.status_code == 200
    (ev,) = await _events(security_events_on, "config_changed")
    assert ev.details == {"method": "POST", "path": "/admin/permissions/groups", "status": 201}


def test_audited_write_paths():
    from utils.security_events import is_audited_write as w
    assert w("POST", "/admin/groups")
    assert w("PUT", "/admin/auth-settings/ldap")
    assert w("PUT", "/plugins/shodan/settings")
    assert w("PUT", "/ai/settings")
    assert w("DELETE", "/marking-profiles/x")
    assert not w("GET", "/admin/groups")
    assert not w("PATCH", "/admin/users/x")           # handler records a richer event
    assert not w("DELETE", "/admin/api-tokens/x")     # likewise
    assert not w("POST", "/admin/security/users/x/disable")
    assert not w("POST", "/admin/auth-settings/smtp/test")
    assert not w("POST", "/ai/chat")
    assert not w("POST", "/findings")


async def test_recording_failure_never_breaks_request(client, make_user, monkeypatch):
    from utils import security_events

    def boom():
        raise RuntimeError("db down")
    monkeypatch.setattr(security_events, "_enabled", True)
    monkeypatch.setattr(security_events, "_session_factory", boom)
    r = await client.post("/auth/login", json={"username": "nobody", "password": "x"})
    assert r.status_code == 401


# ── Ingestion ───────────────────────────────────────────────────────────────

def _line(path="/", status=200, ua="Mozilla/5.0", ip="198.51.100.7", ts="2026-11-08T10:15:00+00:00"):
    return json.dumps({"ts": ts, "ip": ip, "method": "GET", "path": path, "status": status,
                       "bytes": 10, "rt": 0.012, "host": "example.test", "ref": "", "ua": ua}) + "\n"


def test_classify():
    from utils.http_log_ingest import classify
    assert classify("/wp-login.php", "Mozilla") == ["probe"]
    assert classify("/.env", "curl/8.5.0") == ["probe", "tool_ua"]
    assert classify("/.git/config", "Mozilla") == ["probe"]
    assert classify("/api/findings", "sqlmap/1.7") == ["scanner_ua"]
    assert classify("/engagements/123", "Mozilla/5.0") == []
    assert classify("/.well-known/acme-challenge/abc", "Mozilla") == []


@pytest.fixture
def session_factory(db_session):
    class _Ctx:
        async def __aenter__(self):
            return db_session

        async def __aexit__(self, *exc):
            return False
    return lambda: _Ctx()


async def test_ingest_reads_incrementally_and_rolls_up(tmp_path, db_session, session_factory):
    from utils.http_log_ingest import ingest_once
    log = tmp_path / "access.json"
    log.write_text(_line("/") + _line("/wp-login.php", 404, "sqlmap/1.7") + '{"partial":')
    assert await ingest_once(session_factory, str(log)) == 2
    with open(log, "a") as f:
        f.write(' "line"}\n' + _line("/api/health", 503, ts="2026-11-08T11:01:00+00:00"))
    assert await ingest_once(session_factory, str(log)) == 1  # the broken line is skipped, not re-read
    assert await ingest_once(session_factory, str(log)) == 0

    rows = (await db_session.execute(select(HttpRequestLog).order_by(HttpRequestLog.ts))).scalars().all()
    assert [(r.path, r.status, r.area, r.flags) for r in rows] == [
        ("/", 200, "web", None), ("/wp-login.php", 404, "web", "probe,scanner_ua"), ("/api/health", 503, "api", None)]
    assert rows[0].ts == datetime(2026, 11, 8, 10, 15) and rows[0].duration_ms == 12
    hours = {h.bucket.hour: h for h in (await db_session.execute(select(HttpTrafficHourly))).scalars()}
    assert (hours[10].requests, hours[10].s2xx, hours[10].s4xx, hours[10].probes, hours[10].scanner) == (2, 1, 1, 1, 1)
    assert (hours[11].requests, hours[11].s5xx) == (1, 1)


async def test_ingest_truncates_when_caught_up_and_over_cap(tmp_path, db_session, session_factory, monkeypatch):
    from utils import http_log_ingest
    monkeypatch.setattr(http_log_ingest, "MAX_BYTES", 100)
    log = tmp_path / "access.json"
    log.write_text(_line() * 3)
    assert await http_log_ingest.ingest_once(session_factory, str(log)) == 3
    assert log.stat().st_size == 0
    assert (await db_session.get(HttpLogCursor, "nginx")).offset == 0
    log.write_text(_line("/after"))
    assert await http_log_ingest.ingest_once(session_factory, str(log)) == 1


async def test_ingest_restarts_on_rotated_file(tmp_path, db_session, session_factory):
    from utils.http_log_ingest import ingest_once
    log = tmp_path / "access.json"
    log.write_text(_line("/one") + _line("/two"))
    assert await ingest_once(session_factory, str(log)) == 2
    log.unlink()
    log.write_text(_line("/three"))  # new inode, shorter than the old offset
    assert await ingest_once(session_factory, str(log)) == 1


async def test_ingest_missing_file_is_noop(tmp_path, session_factory):
    from utils.http_log_ingest import ingest_once
    assert await ingest_once(session_factory, str(tmp_path / "nope.json")) == 0


# ── Endpoints & gates ───────────────────────────────────────────────────────

VIEW_PATHS = ["/admin/security/overview", "/admin/security/events", "/admin/security/events/summary",
              "/admin/security/accounts", "/admin/security/posture", "/admin/security/traffic/summary",
              "/admin/security/traffic/requests", "/admin/security/traffic/history",
              "/admin/security/audit/activity", "/admin/security/settings"]


@pytest.fixture(autouse=True)
def _offline_posture(monkeypatch):
    """No nginx to talk to in tests; and drop the posture cache between tests."""
    from routers import security_center

    def no_tls(*_a, **_k):
        raise ConnectionRefusedError()
    monkeypatch.setattr(security_center, "_tls_cert_days", no_tls)
    security_center._posture_cache.update(at=0.0, data=None)


@pytest.mark.parametrize("path", VIEW_PATHS)
async def test_operator_cannot_view(client, make_user, authenticate_as, path):
    authenticate_as(await make_user(role="operator"))
    assert (await client.get(path)).status_code == 403


@pytest.mark.parametrize("path", VIEW_PATHS)
async def test_read_only_admin_can_view(client, make_user, authenticate_as, path):
    authenticate_as(await make_user(role="read_only_admin"))
    r = await client.get(path)
    assert r.status_code == 200, r.text


async def test_read_only_admin_cannot_act(client, make_user, authenticate_as):
    target = await make_user(role="operator")
    authenticate_as(await make_user(role="read_only_admin"))
    assert (await client.post(f"/admin/security/users/{target.id}/revoke-sessions")).status_code == 403
    assert (await client.post(f"/admin/security/users/{target.id}/disable")).status_code == 403
    assert (await client.put("/admin/security/settings", json={"http_days": 7})).status_code == 403


async def _grant(db, user, *perms):
    from models.group import Group, user_groups
    from models.permission import GroupPermissions
    g = Group(id=str(uuid.uuid4()), name=f"sec_{uuid.uuid4().hex[:6]}")
    db.add(g)
    await db.flush()
    db.add(GroupPermissions(group_id=g.id, permissions=list(perms)))
    await db.execute(user_groups.insert().values(user_id=user.id, group_id=g.id))
    await db.flush()


async def test_delegated_manager_cannot_act_on_admin(client, db_session, make_user, authenticate_as, monkeypatch):
    import auth.jwt
    monkeypatch.setattr(auth.jwt, "revoke_all_user_tokens", lambda _uid: True)
    mgr = await make_user(role="operator")
    await _grant(db_session, mgr, "view_security_center", "manage_security_center")
    admin = await make_user(role="admin")
    op = await make_user(role="operator")
    authenticate_as(mgr)
    assert (await client.get("/admin/security/accounts")).status_code == 200
    assert (await client.post(f"/admin/security/users/{admin.id}/disable")).status_code == 403
    r = await client.post(f"/admin/security/users/{op.id}/disable")
    assert r.status_code == 200
    await db_session.refresh(op)
    assert op.is_active is False


async def test_disable_self_refused(client, make_user, authenticate_as):
    admin = await make_user(role="admin")
    authenticate_as(admin)
    assert (await client.post(f"/admin/security/users/{admin.id}/disable")).status_code == 400


async def test_revoke_api_token(client, db_session, make_user, authenticate_as, security_events_on):
    from models.api_token import ApiToken
    admin = await make_user(role="admin")
    owner = await make_user(role="operator")
    tok = ApiToken(id=str(uuid.uuid4()), name="ci", token_hash=uuid.uuid4().hex, token_prefix="rw_abcd",
                   permission="rw", user_id=owner.id, created_by=owner.id, is_active=True,
                   created_at=datetime.utcnow())
    db_session.add(tok)
    await db_session.flush()
    authenticate_as(admin)
    accounts = (await client.get("/admin/security/accounts")).json()
    row = next(t for t in accounts["tokens"] if t["id"] == tok.id)
    assert set(row["flags"]) >= {"no_expiry", "read_write"}
    assert (await client.post(f"/admin/security/api-tokens/{tok.id}/revoke")).status_code == 200
    await db_session.refresh(tok)
    assert tok.is_active is False
    (ev,) = await _events(db_session, "api_token_revoked")
    assert ev.user_id == owner.id and ev.actor_id == admin.id


async def test_events_summary_and_filters(client, db_session, make_user, authenticate_as):
    for i in range(3):
        db_session.add(SecurityEvent(event_type="login", outcome="failure", username=f"u{i}", ip="192.0.2.1",
                                     reason="invalid_credentials"))
    db_session.add(SecurityEvent(event_type="login", outcome="success", username="u0", ip="192.0.2.2"))
    await db_session.flush()
    authenticate_as(await make_user(role="admin"))
    s = (await client.get("/admin/security/events/summary")).json()
    assert s["logins_failed"] == 3 and s["logins_ok"] == 1 and s["failing_ips"] == 1
    assert s["top_ips"][0] == {**s["top_ips"][0], "ip": "192.0.2.1", "failures": 3, "usernames": 3}
    r = (await client.get("/admin/security/events", params={"outcome": "failure", "q": "u1"})).json()
    assert r["total"] == 1 and r["items"][0]["username"] == "u1"


async def test_posture_flags_admin_without_mfa(client, make_user, authenticate_as):
    authenticate_as(await make_user(role="admin", username=f"nomfa_{uuid.uuid4().hex[:6]}"))
    data = (await client.get("/admin/security/posture", params={"refresh": True})).json()
    checks = {c["id"]: c for c in data["checks"]}
    assert checks["admin_mfa"]["status"] == "fail"
    assert checks["tls_cert"]["status"] == "info"  # nginx unreachable in tests
    assert {"jwt_secret", "vault_encryption_key", "redis", "cors", "web_logs", "version"} <= set(checks)


async def test_retention_settings_round_trip(client, make_user, authenticate_as):
    authenticate_as(await make_user(role="admin"))
    assert (await client.get("/admin/security/settings")).json()["retention"]["http_days"] == 14
    r = await client.put("/admin/security/settings", json={"http_days": 7})
    assert r.status_code == 200 and r.json()["retention"]["http_days"] == 7
    assert (await client.put("/admin/security/settings", json={"http_days": 0})).status_code == 422
