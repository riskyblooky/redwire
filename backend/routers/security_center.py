"""
security_center.py — admin Security Center (/admin/security/*).

One place for instance security: sign-in activity (security_events), web
traffic (nginx access log via utils/http_log_ingest), accounts & API tokens,
a configuration posture checklist, and the admin audit trail.

Viewing needs VIEW_SECURITY_CENTER (read-only admins pass); actions —
revoke a token, sign a user out everywhere, disable a user, change
retention — need MANAGE_SECURITY_CENTER. Gated on permissions, never role.
"""

import asyncio
import os
import time
from datetime import datetime, timedelta
from typing import Literal, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from auth.permissions import require_global_permission
from database import get_db
from models.api_token import ApiToken
from models.permission import Permission
from models.security_event import HttpRequestLog, HttpTrafficHourly, SecurityEvent
from models.user import User, UserRole
from utils import http_log_ingest
from utils.security_events import record_security_event

router = APIRouter(prefix="/admin/security", tags=["security-center"])


async def _viewer(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> User:
    await require_global_permission(Permission.VIEW_SECURITY_CENTER, current_user, db)
    return current_user


async def _manager(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> User:
    await require_global_permission(Permission.MANAGE_SECURITY_CENTER, current_user, db)
    return current_user


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() + "Z" if dt else None


def _since(hours: int) -> datetime:
    return datetime.utcnow() - timedelta(hours=hours)


def _hour_buckets(hours: int, rows: dict, empty: dict) -> list[dict]:
    """Every hour in the window, oldest first, with zeros where nothing
    happened — so charts draw a continuous series."""
    end = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
    out = []
    for i in range(min(hours, 24 * 31) - 1, -1, -1):
        b = end - timedelta(hours=i)
        out.append(rows.get(b) or {"bucket": _iso(b), **empty})
    return out


# Events that describe an admin acting on someone/something else.
AUDIT_EVENT_TYPES = (
    "user_created", "user_updated", "user_deleted", "password_reset", "api_token_created",
    "api_token_revoked", "sessions_revoked", "config_changed",
)


def _event_row(e: SecurityEvent, names: dict) -> dict:
    return {
        "id": e.id,
        "created_at": _iso(e.created_at),
        "event_type": e.event_type,
        "outcome": e.outcome,
        "user_id": e.user_id,
        "username": e.username or names.get(e.user_id),
        "actor_id": e.actor_id,
        "actor_username": names.get(e.actor_id),
        "ip": e.ip,
        "user_agent": e.user_agent,
        "reason": e.reason,
        "details": e.details,
    }


async def _usernames(db: AsyncSession, ids) -> dict:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    rows = await db.execute(select(User.id, User.username).where(User.id.in_(ids)))
    return dict(rows.all())


# ── Sign-in & security events ───────────────────────────────────────────────

@router.get("/events")
async def list_events(
    event_type: Optional[str] = None,
    outcome: Optional[Literal["success", "failure", "info"]] = None,
    q: Optional[str] = Query(None, max_length=255, description="Username or IP contains"),
    ip: Optional[str] = Query(None, max_length=64),
    user_id: Optional[str] = None,
    audit: bool = Query(False, description="Only admin-action events"),
    hours: int = Query(24 * 7, ge=1, le=24 * 400),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _: User = Depends(_viewer),
    db: AsyncSession = Depends(get_db),
):
    conds = [SecurityEvent.created_at >= _since(hours)]
    if event_type:
        conds.append(SecurityEvent.event_type.in_(event_type.split(",")))
    if audit:
        conds.append(SecurityEvent.event_type.in_(AUDIT_EVENT_TYPES))
    if outcome:
        conds.append(SecurityEvent.outcome == outcome)
    if ip:
        conds.append(SecurityEvent.ip == ip)
    if user_id:
        conds.append(or_(SecurityEvent.user_id == user_id, SecurityEvent.actor_id == user_id))
    if q:
        like = f"%{q}%"
        conds.append(or_(SecurityEvent.username.ilike(like), SecurityEvent.ip.ilike(like),
                         SecurityEvent.reason.ilike(like)))
    where = and_(*conds)
    total = (await db.execute(select(func.count()).select_from(SecurityEvent).where(where))).scalar_one()
    rows = (await db.execute(
        select(SecurityEvent).where(where).order_by(SecurityEvent.created_at.desc()).limit(limit).offset(offset)
    )).scalars().all()
    names = await _usernames(db, [r.user_id for r in rows] + [r.actor_id for r in rows])
    return {"items": [_event_row(r, names) for r in rows], "total": total}


async def _signin_summary(db: AsyncSession, hours: int) -> dict:
    since = _since(hours)
    base = and_(SecurityEvent.created_at >= since)
    counts = (await db.execute(
        select(SecurityEvent.event_type, SecurityEvent.outcome, func.count())
        .where(base).group_by(SecurityEvent.event_type, SecurityEvent.outcome)
    )).all()
    by = {f"{t}:{o}": n for t, o, n in counts}
    failures = and_(base, or_(
        and_(SecurityEvent.event_type == "login", SecurityEvent.outcome == "failure"),
        SecurityEvent.event_type == "mfa_challenge",
    ))
    top_ips = (await db.execute(
        select(SecurityEvent.ip, func.count().label("n"),
               func.count(func.distinct(SecurityEvent.username)).label("users"),
               func.max(SecurityEvent.created_at).label("last"))
        .where(failures, SecurityEvent.ip.isnot(None))
        .group_by(SecurityEvent.ip).order_by(func.count().desc()).limit(10)
    )).all()
    top_users = (await db.execute(
        select(SecurityEvent.username, func.count().label("n"),
               func.count(func.distinct(SecurityEvent.ip)).label("ips"),
               func.max(SecurityEvent.created_at).label("last"))
        .where(failures, SecurityEvent.username.isnot(None))
        .group_by(SecurityEvent.username).order_by(func.count().desc()).limit(10)
    )).all()
    bucket = func.date_trunc("hour", SecurityEvent.created_at)
    series = (await db.execute(
        select(bucket, SecurityEvent.outcome, func.count())
        .where(base, SecurityEvent.event_type == "login").group_by(bucket, SecurityEvent.outcome)
    )).all()
    hourly: dict = {}
    for b, o, n in series:
        hourly.setdefault(b, {"bucket": _iso(b), "success": 0, "failure": 0})[o] = n
    distinct_fail_ips = (await db.execute(
        select(func.count(func.distinct(SecurityEvent.ip))).where(failures)
    )).scalar_one()
    return {
        "hours": hours,
        "logins_ok": by.get("login:success", 0),
        "logins_failed": by.get("login:failure", 0),
        "mfa_failed": by.get("mfa_challenge:failure", 0),
        "rate_limited": by.get("rate_limited:failure", 0),
        "failing_ips": distinct_fail_ips,
        "counts": by,
        "top_ips": [{"ip": i, "failures": n, "usernames": u, "last": _iso(l)} for i, n, u, l in top_ips],
        "top_usernames": [{"username": u, "failures": n, "ips": i, "last": _iso(l)} for u, n, i, l in top_users],
        "hourly": _hour_buckets(hours, hourly, {"success": 0, "failure": 0}),
    }


@router.get("/events/summary")
async def events_summary(
    hours: int = Query(24, ge=1, le=24 * 90),
    _: User = Depends(_viewer),
    db: AsyncSession = Depends(get_db),
):
    return await _signin_summary(db, hours)


# ── Web traffic ─────────────────────────────────────────────────────────────

async def _traffic_summary(db: AsyncSession, hours: int) -> dict:
    since = _since(hours)
    w = HttpRequestLog.ts >= since
    agg = (await db.execute(select(
        func.count(),
        func.count(func.distinct(HttpRequestLog.ip)),
        func.count().filter(HttpRequestLog.status.between(400, 499)),
        func.count().filter(HttpRequestLog.status >= 500),
        func.count().filter(HttpRequestLog.status == 429),
        func.count().filter(HttpRequestLog.flags.like("%probe%")),
        func.count().filter(HttpRequestLog.flags.like("%scanner_ua%")),
    ).where(w))).one()

    async def top(col, extra=None, n=10):
        q = select(col, func.count().label("n")).where(w, col.isnot(None))
        if extra is not None:
            q = q.where(extra)
        return [{"value": v, "count": c} for v, c in
                (await db.execute(q.group_by(col).order_by(func.count().desc()).limit(n))).all()]

    top_ips = (await db.execute(
        select(HttpRequestLog.ip, func.count(),
               func.count().filter(HttpRequestLog.status >= 400),
               func.count().filter(HttpRequestLog.flags.isnot(None)),
               func.max(HttpRequestLog.ts))
        .where(w, HttpRequestLog.ip.isnot(None))
        .group_by(HttpRequestLog.ip).order_by(func.count().desc()).limit(15)
    )).all()
    bucket = func.date_trunc("hour", HttpRequestLog.ts)
    series = (await db.execute(
        select(bucket, func.count(),
               func.count().filter(HttpRequestLog.status.between(400, 499)),
               func.count().filter(HttpRequestLog.status >= 500),
               func.count().filter(HttpRequestLog.flags.isnot(None)))
        .where(w).group_by(bucket).order_by(bucket)
    )).all()
    return {
        "hours": hours,
        "requests": agg[0], "unique_ips": agg[1], "s4xx": agg[2], "s5xx": agg[3],
        "s429": agg[4], "probes": agg[5], "scanner": agg[6],
        "top_ips": [{"ip": i, "requests": n, "errors": e, "flagged": f, "last": _iso(l)}
                    for i, n, e, f, l in top_ips],
        "top_404": await top(HttpRequestLog.path, HttpRequestLog.status == 404),
        "top_probes": await top(HttpRequestLog.path, HttpRequestLog.flags.like("%probe%")),
        "top_user_agents": await top(HttpRequestLog.user_agent),
        "flagged_user_agents": await top(HttpRequestLog.user_agent, HttpRequestLog.flags.like("%_ua%")),
        "top_5xx": await top(HttpRequestLog.path, HttpRequestLog.status >= 500),
        "hourly": _hour_buckets(hours, {b: {"bucket": _iso(b), "requests": n, "s4xx": c4, "s5xx": c5, "flagged": fl}
                                        for b, n, c4, c5, fl in series},
                                {"requests": 0, "s4xx": 0, "s5xx": 0, "flagged": 0}),
    }


@router.get("/traffic/summary")
async def traffic_summary(
    hours: int = Query(24, ge=1, le=24 * 30),
    _: User = Depends(_viewer),
    db: AsyncSession = Depends(get_db),
):
    out = await _traffic_summary(db, hours)
    out["ingest"] = await http_log_ingest.status(db)
    return out


@router.get("/traffic/requests")
async def traffic_requests(
    ip: Optional[str] = Query(None, max_length=64),
    path: Optional[str] = Query(None, max_length=500, description="Path contains"),
    status_code: Optional[str] = Query(None, alias="status", pattern=r"^([1-5]xx|\d{3})$"),
    flag: Optional[Literal["any", "probe", "scanner_ua", "tool_ua"]] = None,
    area: Optional[Literal["web", "api", "ws"]] = None,
    hours: int = Query(24, ge=1, le=24 * 30),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _: User = Depends(_viewer),
    db: AsyncSession = Depends(get_db),
):
    conds = [HttpRequestLog.ts >= _since(hours)]
    if ip:
        conds.append(HttpRequestLog.ip == ip)
    if path:
        conds.append(HttpRequestLog.path.ilike(f"%{path}%"))
    if status_code:
        if status_code.endswith("xx"):
            lo = int(status_code[0]) * 100
            conds.append(HttpRequestLog.status.between(lo, lo + 99))
        else:
            conds.append(HttpRequestLog.status == int(status_code))
    if flag == "any":
        conds.append(HttpRequestLog.flags.isnot(None))
    elif flag:
        conds.append(HttpRequestLog.flags.like(f"%{flag}%"))
    if area:
        conds.append(HttpRequestLog.area == area)
    where = and_(*conds)
    total = (await db.execute(select(func.count()).select_from(HttpRequestLog).where(where))).scalar_one()
    rows = (await db.execute(
        select(HttpRequestLog).where(where).order_by(HttpRequestLog.ts.desc()).limit(limit).offset(offset)
    )).scalars().all()
    return {"total": total, "items": [{
        "id": r.id, "ts": _iso(r.ts), "ip": r.ip, "method": r.method, "path": r.path,
        "status": r.status, "bytes": r.bytes, "duration_ms": r.duration_ms, "host": r.host,
        "user_agent": r.user_agent, "referer": r.referer, "area": r.area,
        "flags": r.flags.split(",") if r.flags else [],
    } for r in rows]}


@router.get("/traffic/history")
async def traffic_history(
    days: int = Query(30, ge=1, le=366),
    _: User = Depends(_viewer),
    db: AsyncSession = Depends(get_db),
):
    """Daily totals from the hourly rollups (outlives raw-log retention)."""
    day = func.date_trunc("day", HttpTrafficHourly.bucket)
    rows = (await db.execute(
        select(day, func.sum(HttpTrafficHourly.requests), func.sum(HttpTrafficHourly.s4xx),
               func.sum(HttpTrafficHourly.s5xx), func.sum(HttpTrafficHourly.s429),
               func.sum(HttpTrafficHourly.probes), func.sum(HttpTrafficHourly.scanner))
        .where(HttpTrafficHourly.bucket >= datetime.utcnow() - timedelta(days=days))
        .group_by(day).order_by(day)
    )).all()
    return [{"day": _iso(d), "requests": int(r or 0), "s4xx": int(a or 0), "s5xx": int(b or 0),
             "s429": int(c or 0), "probes": int(p or 0), "scanner": int(s or 0)}
            for d, r, a, b, c, p, s in rows]


# ── Accounts & API tokens ───────────────────────────────────────────────────

DORMANT_DAYS = 90
STALE_TOKEN_DAYS = 30
_PRIVILEGED = (UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD)


@router.get("/accounts")
async def accounts(_: User = Depends(_viewer), db: AsyncSession = Depends(get_db)):
    now = datetime.utcnow()
    users = (await db.execute(select(User).order_by(User.username))).scalars().all()
    # Most recent successful sign-in (IP) and failures in the last 24h, per user.
    last_ok = dict((await db.execute(
        select(SecurityEvent.user_id, SecurityEvent.ip)
        .where(SecurityEvent.event_type == "login", SecurityEvent.outcome == "success")
        .distinct(SecurityEvent.user_id)
        .order_by(SecurityEvent.user_id, SecurityEvent.created_at.desc())
    )).all())
    fails = dict((await db.execute(
        select(SecurityEvent.user_id, func.count())
        .where(SecurityEvent.event_type.in_(("login", "mfa_challenge")), SecurityEvent.outcome == "failure",
               SecurityEvent.created_at >= now - timedelta(hours=24), SecurityEvent.user_id.isnot(None))
        .group_by(SecurityEvent.user_id)
    )).all())
    tokens = (await db.execute(
        select(ApiToken, User.username).join(User, ApiToken.user_id == User.id)
        .order_by(ApiToken.created_at.desc())
    )).all()
    tokens_by_user: dict = {}
    for t, _u in tokens:
        if t.is_active:
            tokens_by_user[t.user_id] = tokens_by_user.get(t.user_id, 0) + 1

    def dormant(u: User) -> bool:
        ref = u.last_login or u.created_at
        return bool(u.is_active and ref and ref < now - timedelta(days=DORMANT_DAYS))

    out_users = [{
        "id": u.id, "username": u.username, "full_name": u.full_name, "email": u.email,
        "role": u.role.value if u.role else None, "is_active": u.is_active,
        "auth_provider": u.auth_provider or "local", "mfa": bool(u.totp_enabled),
        "last_login": _iso(u.last_login), "last_active": _iso(u.last_active),
        "created_at": _iso(u.created_at), "last_ip": last_ok.get(u.id),
        "failed_24h": fails.get(u.id, 0), "active_tokens": tokens_by_user.get(u.id, 0),
        "privileged": u.role in _PRIVILEGED, "dormant": dormant(u),
        "must_change_password": bool(u.must_change_password),
    } for u in users]

    def token_flags(t: ApiToken) -> list[str]:
        f = []
        if not t.is_active:
            return ["revoked"]
        if t.expires_at and t.expires_at < now:
            return ["expired"]
        if not t.expires_at:
            f.append("no_expiry")
        if t.permission == "rw":
            f.append("read_write")
        if (t.last_used_at or t.created_at) < now - timedelta(days=STALE_TOKEN_DAYS):
            f.append("unused")
        return f

    return {
        "users": out_users,
        "tokens": [{
            "id": t.id, "name": t.name, "token_prefix": t.token_prefix, "permission": t.permission,
            "user_id": t.user_id, "username": uname, "created_at": _iso(t.created_at),
            "last_used_at": _iso(t.last_used_at), "expires_at": _iso(t.expires_at),
            "is_active": t.is_active, "flags": token_flags(t),
        } for t, uname in tokens],
        "dormant_days": DORMANT_DAYS,
        "stale_token_days": STALE_TOKEN_DAYS,
    }


async def _target_user(db: AsyncSession, user_id: str, actor: User) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    # A delegated security manager must not be able to lock out an admin.
    if user.role == UserRole.ADMIN and actor.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only an admin can act on an admin account")
    return user


@router.post("/users/{user_id}/revoke-sessions")
async def revoke_sessions(
    user_id: str, request: Request,
    current_user: User = Depends(_manager), db: AsyncSession = Depends(get_db),
):
    """Sign the user out everywhere: every access/refresh token issued so far
    stops working. API tokens are separate (revoke them individually)."""
    from auth.jwt import revoke_all_user_tokens
    user = await _target_user(db, user_id, current_user)
    if not revoke_all_user_tokens(user.id):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Session revocation failed. Please retry.")
    await record_security_event("sessions_revoked", request=request, user=user, actor=current_user,
                                details={"via": "security_center"})
    return {"ok": True}


@router.post("/users/{user_id}/disable")
async def disable_user(
    user_id: str, request: Request,
    current_user: User = Depends(_manager), db: AsyncSession = Depends(get_db),
):
    """Deactivate the account and revoke its sessions (re-enable from Users)."""
    from auth.jwt import revoke_all_user_tokens
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="You can't disable your own account")
    user = await _target_user(db, user_id, current_user)
    user.is_active = False
    await db.commit()
    if not revoke_all_user_tokens(user.id):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Account disabled, but session revocation failed. Please retry.")
    await record_security_event("user_updated", request=request, user=user, actor=current_user,
                                details={"changes": {"is_active": {"old": True, "new": False}},
                                         "sessions_revoked": True, "via": "security_center"})
    return {"ok": True}


@router.post("/api-tokens/{token_id}/revoke")
async def revoke_api_token(
    token_id: str, request: Request,
    current_user: User = Depends(_manager), db: AsyncSession = Depends(get_db),
):
    token = await db.get(ApiToken, token_id)
    if token is None:
        raise HTTPException(status_code=404, detail="Token not found")
    await _target_user(db, token.user_id, current_user)
    token.is_active = False
    await db.commit()
    await record_security_event("api_token_revoked", request=request, user_id=token.user_id,
                                actor=current_user,
                                details={"token_prefix": token.token_prefix, "via": "security_center"})
    return {"ok": True}


# ── Admin audit (sensitive activity-log actions) ────────────────────────────

SENSITIVE_ACTIONS = (
    "updated_setting", "exported_engagement_with_secrets", "accessed_vault_secret",
    "deleted_engagement", "consumed_recovery_code", "issued_recovery_codes",
    "cleared_recovery_codes", "regenerated_recovery_codes",
)


@router.get("/audit/activity")
async def sensitive_activity(
    hours: int = Query(24 * 30, ge=1, le=24 * 400),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _: User = Depends(_viewer),
    db: AsyncSession = Depends(get_db),
):
    """Security-sensitive actions from the activity log: secret reveals,
    exports with secrets, engagement deletions, setting changes, recovery
    codes."""
    from models.discussion import ActivityLog
    where = and_(ActivityLog.action.in_(SENSITIVE_ACTIONS), ActivityLog.created_at >= _since(hours))
    total = (await db.execute(select(func.count()).select_from(ActivityLog).where(where))).scalar_one()
    rows = (await db.execute(
        select(ActivityLog).where(where).order_by(ActivityLog.created_at.desc()).limit(limit).offset(offset)
    )).scalars().all()
    names = await _usernames(db, [r.user_id for r in rows])
    return {"total": total, "items": [{
        "id": r.id, "created_at": _iso(r.created_at), "action": r.action, "user_id": r.user_id,
        "username": names.get(r.user_id), "resource_type": r.resource_type, "resource_id": r.resource_id,
        "resource_name": r.resource_name, "engagement_id": r.engagement_id or r.origin_engagement_id,
        "details": r.details,
    } for r in rows]}


# ── Posture ─────────────────────────────────────────────────────────────────

def _check(cid: str, title: str, status_: str, detail: str, fix: str = "", category: str = "Configuration") -> dict:
    return {"id": cid, "title": title, "status": status_, "detail": detail, "fix": fix, "category": category}


def _tls_cert_days(host: str, server: str = "nginx", port: int = 443) -> tuple[Optional[int], Optional[str], bool]:
    """(days until expiry, issuer CN, self-signed) of the certificate nginx serves."""
    import socket
    import ssl
    from cryptography import x509
    from cryptography.x509.oid import NameOID

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with socket.create_connection((server, port), timeout=3) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as tls:
            der = tls.getpeercert(binary_form=True)
    cert = x509.load_der_x509_certificate(der)
    expires = getattr(cert, "not_valid_after_utc", None) or cert.not_valid_after
    expires = expires.replace(tzinfo=None)
    issuer = cert.issuer.get_attributes_for_oid(NameOID.COMMON_NAME)
    return (expires - datetime.utcnow()).days, (issuer[0].value if issuer else None), cert.issuer == cert.subject


_posture_cache: dict = {"at": 0.0, "data": None}
_POSTURE_TTL = 300


async def _posture(db: AsyncSession, refresh: bool = False) -> dict:
    if not refresh and _posture_cache["data"] and time.monotonic() - _posture_cache["at"] < _POSTURE_TTL:
        return _posture_cache["data"]

    from auth.jwt import SECRET_KEY
    from auth.password import verify_password
    from models.auth_settings import AuthSetting
    from models.plugin import PluginSetting
    from models.registration_code import RegistrationCode
    from utils.cluster import async_redis
    from version import VERSION

    checks: list[dict] = []
    now = datetime.utcnow()
    settings = {s.key: (s.value or "") for s in (await db.execute(select(AuthSetting))).scalars().all()}
    on = lambda k, default="false": settings.get(k, default).lower() == "true"  # noqa: E731

    # Secrets & keys
    if SECRET_KEY == "your-secret-key-change-in-production":
        checks.append(_check("jwt_secret", "JWT signing secret", "fail", "JWT_SECRET is the shipped default — anyone can forge sessions.",
                             "Set a long random JWT_SECRET in .env and restart (signs everyone out).", "Secrets"))
    elif len(SECRET_KEY) < 32:
        checks.append(_check("jwt_secret", "JWT signing secret", "warn", f"JWT_SECRET is only {len(SECRET_KEY)} characters.",
                             "Use at least 32 random characters (e.g. `openssl rand -hex 32`).", "Secrets"))
    else:
        checks.append(_check("jwt_secret", "JWT signing secret", "pass", "Custom secret of adequate length.", category="Secrets"))

    for env, title, why in (
        ("VAULT_ENCRYPTION_KEY", "Vault encryption key", "Credential vault contents"),
        ("TOTP_ENCRYPTION_KEY", "2FA secret encryption key", "Users' TOTP secrets"),
    ):
        raw = os.getenv(env, "").strip()
        try:
            from cryptography.fernet import Fernet
            Fernet(raw.encode())
            checks.append(_check(env.lower(), title, "pass", f"{why} are encrypted with a valid key. Back it up separately from the database.", category="Secrets"))
        except Exception:
            checks.append(_check(env.lower(), title, "fail", f"{env} is missing or not a valid Fernet key.",
                                 f"Generate one with `python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`.", "Secrets"))

    secrets_plain = (await db.execute(
        select(func.count()).select_from(PluginSetting)
        .where(PluginSetting.is_secret.is_(True), PluginSetting.value.isnot(None), PluginSetting.value != "")
    )).scalar_one()
    checks.append(_check("plugin_secrets", "Plugin secret settings", "warn" if secrets_plain else "pass",
                         f"{secrets_plain} plugin secret value(s) stored unencrypted in the database." if secrets_plain
                         else "No plugin secrets stored.",
                         "Plugin secrets (API keys, passwords) are masked in the UI but stored in plaintext; limit database access accordingly." if secrets_plain else "",
                         "Secrets"))

    # Accounts
    admins = (await db.execute(select(User).where(User.is_active.is_(True), User.role.in_(_PRIVILEGED)))).scalars().all()
    # LDAP sign-ins go through RedWire's own 2FA; only SAML defers MFA to the IdP.
    local_admins = [a for a in admins if (a.auth_provider or "local") != "saml"]
    no_mfa_admins = [a.username for a in local_admins if a.role == UserRole.ADMIN and not a.totp_enabled]
    no_mfa_priv = [a.username for a in local_admins if a.role != UserRole.ADMIN and not a.totp_enabled]
    if no_mfa_admins:
        checks.append(_check("admin_mfa", "Admins use 2FA", "fail", f"Admins without 2FA: {', '.join(no_mfa_admins)}.",
                             "Each admin enables two-factor authentication on their Profile page.", "Accounts"))
    elif no_mfa_priv:
        checks.append(_check("admin_mfa", "Admins use 2FA", "warn", f"Privileged users without 2FA: {', '.join(no_mfa_priv)}.",
                             "Team leads and read-only admins should enable 2FA too.", "Accounts"))
    else:
        checks.append(_check("admin_mfa", "Admins use 2FA", "pass", "Every non-SSO privileged account has 2FA.", category="Accounts"))

    weak = []
    for a in local_admins:
        if a.hashed_password and await asyncio.to_thread(verify_password, "changeme", a.hashed_password):
            weak.append(a.username)
    checks.append(_check("default_password", "Default admin password", "fail" if weak else "pass",
                         f"Still using the default password: {', '.join(weak)}." if weak else "No privileged account uses the default password.",
                         "Change the password now." if weak else "", "Accounts"))

    active_local = (await db.execute(select(func.count(), func.count().filter(User.totp_enabled.is_(True)))
                                     .where(User.is_active.is_(True), func.coalesce(User.auth_provider, "local") != "saml"))).one()
    pct = round(100 * active_local[1] / active_local[0]) if active_local[0] else 100
    checks.append(_check("user_mfa", "2FA adoption", "pass" if pct >= 80 else "warn" if pct >= 30 else "fail",
                         f"{active_local[1]} of {active_local[0]} active non-SSO users ({pct}%) have 2FA.",
                         "" if pct >= 80 else "Encourage or require 2FA; consider SSO with IdP-enforced MFA.", "Accounts"))

    dormant = (await db.execute(select(func.count()).select_from(User).where(
        User.is_active.is_(True), func.coalesce(User.last_login, User.created_at) < now - timedelta(days=DORMANT_DAYS)
    ))).scalar_one()
    checks.append(_check("dormant", "Dormant accounts", "warn" if dormant else "pass",
                         f"{dormant} active account(s) haven't signed in for {DORMANT_DAYS}+ days." if dormant else "No dormant active accounts.",
                         "Disable accounts that are no longer needed (Accounts tab)." if dormant else "", "Accounts"))

    tok = (await db.execute(select(
        func.count().filter(ApiToken.expires_at.is_(None)),
        func.count().filter(func.coalesce(ApiToken.last_used_at, ApiToken.created_at) < now - timedelta(days=STALE_TOKEN_DAYS)),
    ).where(ApiToken.is_active.is_(True), or_(ApiToken.expires_at.is_(None), ApiToken.expires_at > now)))).one()
    checks.append(_check("api_tokens", "API tokens", "warn" if (tok[0] or tok[1]) else "pass",
                         f"{tok[0]} active token(s) never expire; {tok[1]} unused for {STALE_TOKEN_DAYS}+ days." if (tok[0] or tok[1])
                         else "All active tokens expire and are in use.",
                         "Revoke unused tokens and set expiries (Accounts tab)." if (tok[0] or tok[1]) else "", "Accounts"))

    codes = (await db.execute(select(
        func.count(), func.count().filter(RegistrationCode.expires_at.is_(None)),
    ).where(RegistrationCode.is_active.is_(True), RegistrationCode.used_count < RegistrationCode.max_uses,
            or_(RegistrationCode.expires_at.is_(None), RegistrationCode.expires_at > now)))).one()
    checks.append(_check("registration_codes", "Open registration codes", "warn" if codes[1] else "info" if codes[0] else "pass",
                         f"{codes[0]} usable registration code(s), {codes[1]} with no expiry." if codes[0] else "No usable registration codes — self-registration is closed.",
                         "Give codes an expiry, or deactivate them when onboarding is done." if codes[1] else "", "Accounts"))

    # Identity providers & mail
    if on("ldap_enabled"):
        url = settings.get("ldap_server_url", "")
        tls = url.lower().startswith("ldaps://") or on("ldap_tls_enabled")
        checks.append(_check("ldap_tls", "LDAP transport", "pass" if tls else "fail",
                             "LDAP uses TLS." if tls else "LDAP binds travel unencrypted (ldap:// without StartTLS).",
                             "" if tls else "Use ldaps:// or enable StartTLS (Admin → Authentication).", "Identity"))
        if not on("ldap_tls_verify", "true"):
            checks.append(_check("ldap_verify", "LDAP certificate verification", "warn", "Server certificate is not verified.",
                                 "Enable verification and supply the CA certificate.", "Identity"))
        if on("ldap_debug_enabled"):
            checks.append(_check("ldap_debug", "LDAP debug logging", "warn", "LDAP debug logging is on (verbose directory details in logs).",
                                 "Turn it off when troubleshooting is done.", "Identity"))
    if on("saml_enabled") and not on("saml_want_messages_signed", "true"):
        checks.append(_check("saml_signed", "SAML message signing", "warn", "Unsigned SAML messages are accepted.",
                             "Require signed messages from the IdP.", "Identity"))
    if on("smtp_enabled"):
        tls = on("smtp_use_tls", "true") or settings.get("smtp_port") == "465"
        checks.append(_check("smtp_tls", "SMTP transport", "pass" if tls else "warn",
                             "Mail is sent over TLS." if tls else "Mail (including password-reset links) is sent without TLS.",
                             "" if tls else "Enable TLS for SMTP.", "Identity"))
        if not on("smtp_tls_verify", "true"):
            checks.append(_check("smtp_verify", "SMTP certificate verification", "warn", "Mail server certificate is not verified.",
                                 "Enable verification.", "Identity"))

    # Platform
    origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
    bad = [o for o in origins if o == "*"]
    plain = [o for o in origins if o.startswith("http://") and not any(h in o for h in ("localhost", "127.0.0.1"))]
    checks.append(_check("cors", "CORS origins", "fail" if bad else "warn" if plain else "pass",
                         "Wildcard origin allowed with credentials." if bad else
                         f"Plain-HTTP origins allowed: {', '.join(plain)}." if plain else
                         f"{len(origins) or 'Default'} origin(s), all HTTPS or local.",
                         "Restrict CORS_ORIGINS to the site's https:// URL." if (bad or plain) else "", "Platform"))

    redis_ok = await async_redis() is not None
    checks.append(_check("redis", "Redis (session revocation, rate limits)", "pass" if redis_ok else "fail",
                         "Reachable." if redis_ok else "Unreachable — sign-out, revocation and rate limiting can't be enforced.",
                         "" if redis_ok else "Check the redis container and REDIS_URL.", "Platform"))

    host = urlparse(os.getenv("FRONTEND_URL", "")).hostname or os.getenv("DOMAIN_NAME", "localhost")
    try:
        days, issuer, self_signed = await asyncio.to_thread(_tls_cert_days, host)
        st = "fail" if days < 14 else "warn" if (days < 30 or self_signed) else "pass"
        checks.append(_check("tls_cert", "TLS certificate", st,
                             f"Expires in {days} days; issuer {issuer or 'unknown'}{' (self-signed)' if self_signed else ''}.",
                             "Check the certbot container — renewals should happen ~30 days before expiry." if days < 30
                             else "Self-signed: browsers will warn. Use Let's Encrypt (scripts/init-ssl) in production." if self_signed else "",
                             "Platform"))
    except Exception as e:
        checks.append(_check("tls_cert", "TLS certificate", "info", f"Couldn't read the certificate from nginx ({e.__class__.__name__}).",
                             category="Platform"))

    ingest = await http_log_ingest.status(db)
    if not ingest["configured"]:
        checks.append(_check("web_logs", "Web traffic logging", "warn", "nginx's JSON access log isn't available to the backend, so Web traffic is empty.",
                             "Redeploy with the current docker-compose.yml (nginx_logs volume).", "Platform"))
    else:
        last = ingest["last_ingest"]
        checks.append(_check("web_logs", "Web traffic logging", "pass", f"Ingesting; last pass {last or 'pending'}.", category="Platform"))

    checks.append(_check("version", "RedWire version", "info", f"Running {VERSION}.",
                         "Compare with the latest release on GitHub.", "Platform"))

    tally = {s: sum(1 for c in checks if c["status"] == s) for s in ("pass", "warn", "fail", "info")}
    data = {"checks": checks, "tally": tally, "generated_at": _iso(now)}
    _posture_cache.update(at=time.monotonic(), data=data)
    return data


@router.get("/posture")
async def posture(
    refresh: bool = False,
    _: User = Depends(_viewer),
    db: AsyncSession = Depends(get_db),
):
    return await _posture(db, refresh=refresh)


# ── Overview ────────────────────────────────────────────────────────────────

BRUTE_FORCE_THRESHOLD = 10  # failures from one IP in 24h


@router.get("/overview")
async def overview(_: User = Depends(_viewer), db: AsyncSession = Depends(get_db)):
    from version import VERSION
    signins = await _signin_summary(db, 24)
    traffic = await _traffic_summary(db, 24)
    post = await _posture(db)
    attention = []
    for c in post["checks"]:
        if c["status"] in ("fail", "warn"):
            attention.append({"severity": "high" if c["status"] == "fail" else "medium",
                              "title": c["title"], "detail": c["detail"], "tab": "posture"})
    for ip in signins["top_ips"]:
        if ip["failures"] >= BRUTE_FORCE_THRESHOLD:
            attention.append({"severity": "high", "title": f"Repeated sign-in failures from {ip['ip']}",
                              "detail": f"{ip['failures']} failures across {ip['usernames']} username(s) in 24h.",
                              "tab": "signins", "ip": ip["ip"]})
    if traffic["s5xx"]:
        attention.append({"severity": "medium", "title": "Server errors",
                          "detail": f"{traffic['s5xx']} 5xx responses in the last 24h.", "tab": "traffic"})
    attention.sort(key=lambda a: 0 if a["severity"] == "high" else 1)
    return {
        "version": VERSION,
        "signins": {k: signins[k] for k in ("logins_ok", "logins_failed", "mfa_failed", "rate_limited", "failing_ips", "hourly")},
        "traffic": {k: traffic[k] for k in ("requests", "unique_ips", "s4xx", "s5xx", "s429", "probes", "scanner", "hourly")},
        "posture": post["tally"],
        "tls": next((c for c in post["checks"] if c["id"] == "tls_cert"), None),
        "attention": attention,
    }


# ── Settings ────────────────────────────────────────────────────────────────

class RetentionUpdate(BaseModel):
    http_days: Optional[int] = Field(None, ge=1, le=90)
    events_days: Optional[int] = Field(None, ge=30, le=3650)
    rollup_days: Optional[int] = Field(None, ge=30, le=3650)


@router.get("/settings")
async def get_settings(_: User = Depends(_viewer), db: AsyncSession = Depends(get_db)):
    return {"retention": await http_log_ingest.get_retention(db)}


@router.put("/settings")
async def update_settings(
    body: RetentionUpdate, request: Request,
    current_user: User = Depends(_manager), db: AsyncSession = Depends(get_db),
):
    values = body.model_dump(exclude_none=True)
    retention = await http_log_ingest.set_retention(db, values, current_user.id)
    await record_security_event("config_changed", request=request, user=current_user, actor=current_user,
                                reason="Security Center retention", details={"retention": values})
    return {"retention": retention}
