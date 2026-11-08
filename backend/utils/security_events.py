"""
security_events.py — durable security event log for the admin Security Center.

``record_security_event`` writes one ``SecurityEvent`` row in its own session
(so a failed sign-in is kept even though the request's transaction rolls back
with the 401) and never raises: a logging failure must not change the outcome
of the request it describes.

Event types (``event_type``) and their ``outcome``:
  login              success | failure  (reason: invalid_credentials,
                                          inactive_account, mfa_invalid, ...)
  mfa_challenge      failure            (bad / reused 2FA code at verify-2fa)
  logout             info
  register           success
  password_changed   info               (self-service or forced change)
  password_reset     info               (reset completed / admin reset)
  password_reset_requested  info
  mfa_enabled / mfa_disabled / mfa_recovery_regenerated  info
  sessions_revoked   info               (all of a user's tokens revoked)
  api_token_created / api_token_revoked  info
  user_created / user_updated / user_deleted  info  (details: changed fields)
  rate_limited       failure            (HTTP 429; details: path)
  sso_error          failure            (SAML / LDAP problems)
  config_changed     info               (successful write to an admin config
                                          endpoint; see AdminAuditMiddleware)
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Tests turn recording off (conftest) — the app session factory points at the
# real database — and opt back in with their own factory.
_enabled = True
_session_factory = None


def client_ip(request) -> Optional[str]:
    """The client's address as nginx saw it (X-Real-IP is set by nginx and
    overrides any client-supplied value; see rate_limit.py)."""
    if request is None:
        return None
    return request.headers.get("X-Real-IP") or (request.client.host if request.client else None)


async def record_security_event(
    event_type: str,
    *,
    request=None,
    outcome: str = "info",
    user=None,
    user_id: Optional[str] = None,
    username: Optional[str] = None,
    actor=None,
    actor_id: Optional[str] = None,
    reason: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
) -> None:
    if not _enabled:
        return
    try:
        import database
        from models.security_event import SecurityEvent

        factory = _session_factory or database.AsyncSessionLocal
        ua = request.headers.get("User-Agent") if request is not None else None
        async with factory() as db:
            db.add(SecurityEvent(
                event_type=event_type,
                outcome=outcome,
                user_id=user_id or (user.id if user is not None else None),
                username=(username or (user.username if user is not None else None) or None),
                actor_id=actor_id or (actor.id if actor is not None else None),
                ip=client_ip(request),
                user_agent=(ua or "")[:500] or None,
                reason=(reason or "")[:255] or None,
                details=details,
            ))
            await db.commit()
    except Exception as e:  # never let auditing break the request
        logger.warning("security event %s not recorded: %s", event_type, e)


async def prune(db, older_than_days: int) -> int:
    """Delete events older than the retention window; returns rows removed."""
    from datetime import datetime, timedelta
    from sqlalchemy import delete
    from models.security_event import SecurityEvent

    res = await db.execute(
        delete(SecurityEvent).where(SecurityEvent.created_at < datetime.utcnow() - timedelta(days=older_than_days))
    )
    await db.commit()
    return res.rowcount or 0


# ── Admin config audit ──────────────────────────────────────────────────────
# Admin configuration lives behind ~40 write endpoints (groups, roles,
# registration codes, auth/SMTP/SAML settings, plugins, AI, types, custom
# fields, marking profiles, wordlists). Rather than instrument each, this
# middleware records every *successful* write to those paths. User and API
# token changes are excluded — their handlers record richer events.
import re as _re

_AUDITED_WRITE = _re.compile(
    r"^/(admin/(?!users(/|$)|api-tokens(/|$)|security(/|$))"
    r"|plugins/|ai/settings$|configurable-types|custom-field-definitions"
    r"|marking-profiles|client-types|engagement-types|wordlist)"
)
_NOT_A_CHANGE = _re.compile(r"/test$|/preview$|/fetch-models$")


def is_audited_write(method: str, path: str) -> bool:
    return (method in ("POST", "PUT", "PATCH", "DELETE")
            and bool(_AUDITED_WRITE.match(path)) and not _NOT_A_CHANGE.search(path))


class AdminAuditMiddleware:
    """Pure ASGI (no BaseHTTPMiddleware) so streaming responses and
    background tasks are untouched."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not is_audited_write(scope["method"], scope["path"]):
            return await self.app(scope, receive, send)
        status_holder = {}

        async def _send(message):
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
            await send(message)

        await self.app(scope, receive, _send)
        code = status_holder.get("status", 0)
        if 200 <= code < 300:
            from starlette.requests import Request
            request = Request(scope)
            actor_id = scope.get("state", {}).get("auth_user_id")
            await record_security_event(
                "config_changed", request=request, actor_id=actor_id, user_id=actor_id,
                reason=f"{scope['method']} {scope['path']}",
                details={"method": scope["method"], "path": scope["path"], "status": code},
            )
