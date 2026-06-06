from models.discussion import ActivityLog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional, List, Dict, Any
import json
import logging
from fastapi import WebSocket

logger = logging.getLogger(__name__)


async def create_notification(
    db: AsyncSession,
    user_id: str,
    event_type: str,
    title: str,
    message: Optional[str] = None,
    link: Optional[str] = None,
    actor_id: Optional[str] = None,
    engagement_id: Optional[str] = None,
    skip_self_check: bool = False,
):
    """Create a persisted notification for a user.
    
    Checks user preferences and pushes via WebSocket if not site-muted.
    Skips if user_id == actor_id (don't notify yourself), unless skip_self_check is True.
    """
    if not skip_self_check and user_id == actor_id:
        return None

    from models.notification import Notification, NotificationPreference

    # Check preferences
    pref_result = await db.execute(
        select(NotificationPreference).where(
            NotificationPreference.user_id == user_id,
            NotificationPreference.event_type == event_type,
        )
    )
    pref = pref_result.scalar_one_or_none()
    site_muted = pref.site_muted if pref else False

    # Always persist the notification (user can view history)
    notif = Notification(
        user_id=user_id,
        event_type=event_type,
        title=title,
        message=message,
        link=link,
        actor_id=actor_id,
        engagement_id=engagement_id,
    )
    db.add(notif)
    # Note: caller must commit

    # Push via WebSocket if not site-muted
    if not site_muted:
        try:
            await manager.broadcast_to_resource("user", user_id, {
                "type": "notification",
                "notification": {
                    "id": notif.id,
                    "event_type": event_type,
                    "title": title,
                    "message": message,
                    "link": link,
                    "created_at": notif.created_at.isoformat() if notif.created_at else None,
                },
            })
        except Exception as e:
            logger.warning(f"Failed to push notification via WebSocket: {e}")

    return notif


async def notify_engagement_users(
    db: AsyncSession,
    engagement_id: str,
    event_type: str,
    title: str,
    message: Optional[str] = None,
    link: Optional[str] = None,
    actor_id: Optional[str] = None,
):
    """Send a notification to all users assigned to an engagement (excluding the actor)."""
    from models.associations import EngagementAssignment

    result = await db.execute(
        select(EngagementAssignment.user_id).where(
            EngagementAssignment.engagement_id == engagement_id
        )
    )
    user_ids = [row[0] for row in result.all()]

    for uid in user_ids:
        await create_notification(
            db=db,
            user_id=uid,
            event_type=event_type,
            title=title,
            message=message,
            link=link,
            actor_id=actor_id,
            engagement_id=engagement_id,
        )


import re

_MENTION_RE = re.compile(r'@(\w+)')


async def notify_mentions(
    db: AsyncSession,
    content: str,
    actor_id: str,
    title: str,
    message: Optional[str] = None,
    link: Optional[str] = None,
    engagement_id: Optional[str] = None,
):
    """Extract @username mentions from content and send notifications."""
    if not content:
        return

    from models.user import User as UserModel

    # GHSA-82jh-8f6p-vgx9: finditer streams matches into the dedup'd set so
    # peak memory is bounded by the number of *distinct* usernames, not the
    # number of '@' occurrences. The schema-layer max_length is the primary
    # gate; this is defense-in-depth for any future caller that bypasses it.
    usernames = {m.group(1) for m in _MENTION_RE.finditer(content)}
    if not usernames:
        return

    result = await db.execute(
        select(UserModel.id, UserModel.username).where(
            UserModel.username.in_(usernames)
        )
    )
    users = result.all()

    # GHSA-m2wc-pppv-77gf: if there's an engagement context, drop recipients
    # who can't see that engagement, so @mentions can't leak engagement
    # existence / titles or be used as a username-enumeration oracle.
    if engagement_id:
        from auth.rbac import check_engagement_permission
        from models.permission import Permission
        filtered = []
        for uid, uname in users:
            try:
                if await check_engagement_permission(
                    uid, engagement_id, Permission.ENGAGEMENT_VIEW.value, db
                ):
                    filtered.append((uid, uname))
            except Exception:
                continue  # fail closed
        users = filtered

    for uid, _uname in users:
        await create_notification(
            db=db,
            user_id=uid,
            event_type="mention",
            title=title,
            message=message,
            link=link,
            actor_id=actor_id,
            engagement_id=engagement_id,
        )


# Fields where we only note "updated" rather than dumping full old/new text
_LONG_TEXT_FIELDS = {
    "description", "content", "scope", "objectives", "notes",
    "impact", "technical_details", "steps_to_reproduce", "mitigations",
    "references", "steps", "expected_result", "actual_result",
}

# Fields whose values must never appear in activity logs / reports. Sourced
# from utils.vault_crypto so anything encrypted at rest is automatically
# redacted from the diff stream — add new vault-sensitive columns there and
# this set follows.
from utils.vault_crypto import ENCRYPTED_FIELDS as _VAULT_ENCRYPTED_FIELDS
_REDACTED_FIELDS = frozenset(_VAULT_ENCRYPTED_FIELDS)


def build_change_summary(
    old_obj: Any,
    update_data: dict,
    label: str = "Updated",
) -> str:
    """Compare old object attributes against incoming update_data dict.

    Returns a human-readable string like:
        'Updated status: planning → active, name: Old Name → New Name'

    Long text fields just say 'updated <field>' to avoid overwhelming logs.
    Redacted (vault-sensitive) fields say '<field> (changed)' without values.
    Fields whose value did not actually change are omitted.
    """
    parts: list[str] = []
    for field, new_val in update_data.items():
        old_val = getattr(old_obj, field, None)
        if field in _REDACTED_FIELDS:
            # Don't render or compare values — old_val may be ciphertext and
            # new_val is plaintext input; either way, neither must reach logs.
            parts.append(f"{field.replace('_', ' ')} (changed)")
            continue
        # Skip unchanged values
        if old_val == new_val:
            continue
        if field in _LONG_TEXT_FIELDS:
            parts.append(field.replace("_", " "))
        else:
            # Format values nicely
            old_display = _fmt(old_val)
            new_display = _fmt(new_val)
            parts.append(f"{field.replace('_', ' ')}: {old_display} → {new_display}")

    if not parts:
        return f"{label} (no field changes)"
    return f"{label} — {', '.join(parts)}"


def _fmt(val: Any) -> str:
    """Format a value for display in a log message."""
    if val is None:
        return "none"
    if isinstance(val, bool):
        return str(val).lower()
    if isinstance(val, str) and len(val) > 60:
        return f"'{val[:57]}...'"
    return str(val)


async def create_activity_log(
    db: AsyncSession,
    engagement_id: str,
    user_id: str,
    action: str,
    resource_type: str,
    resource_id: str,
    resource_name: Optional[str] = None,
    details: Optional[str] = None,
    extra_context: dict = None,
):
    """Helper to create an activity log entry. Completely non-fatal — never raises.

    This function is self-contained: it commits its own log entry and all
    side-effects internally. Callers do NOT need to commit after calling this.
    """
    import traceback as tb

    # ── 1. Persist the activity log entry ──────────────────────────────
    try:
        log_entry = ActivityLog(
            engagement_id=engagement_id,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            details=details
        )
        db.add(log_entry)
        await db.commit()
    except Exception as e:
        logger.warning(f"create_activity_log: failed to persist log entry: {e}")
        tb.print_exc()
        try:
            await db.rollback()
        except Exception:
            pass
        return  # Don't run side-effects if we can't even log

    # ── 2. WebSocket broadcasts ────────────────────────────────────────
    try:
        event_payload = {
            "type": "activity_log",
            "action": action,
            "resource_type": resource_type,
            "resource_name": resource_name,
            "user_id": user_id,
            "engagement_id": engagement_id,
            "details": details,
        }
        await manager.broadcast_to_resource("engagement", engagement_id, event_payload)
        # dashboard:global is open to any authenticated subscriber, so pass
        # db down — broadcast_to_resource will filter recipients by
        # ENGAGEMENT_VIEW membership against this event's engagement_id.
        await manager.broadcast_to_resource("dashboard", "global", event_payload, db=db)
        await manager.broadcast_to_resource("dashboard", engagement_id, event_payload)
    except Exception as e:
        print(f"[ActivityLog] Broadcast error (non-fatal): {e}")

    # ── 3. Plugin event bus ────────────────────────────────────────────
    try:
        from utils.event_bus import event_bus
        event_name = f"{resource_type}.{action}"
        await event_bus.emit(event_name, {
            "resource_id": resource_id,
            "resource_name": resource_name,
            "resource_type": resource_type,
            "action": action,
            "engagement_id": engagement_id,
            "user_id": user_id,
            "details": details,
        })
    except Exception as e:
        print(f"[ActivityLog] EventBus emit error (non-fatal): {e}")

    # ── 4. Automation engine ───────────────────────────────────────────
    try:
        from utils.automation_engine import evaluate_rules
        context = {
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "resource_name": resource_name,
            "engagement_id": engagement_id,
            "user_id": user_id,
            "details": details,
        }
        if extra_context:
            context.update(extra_context)

        await evaluate_rules(db, action, context)

        # Fire specialized status-change triggers
        if "status" in (extra_context or {}):
            status_trigger = None
            if resource_type == "finding":
                status_trigger = "finding_status_changed"
            elif resource_type == "engagement":
                status_trigger = "engagement_status_changed"
            elif resource_type == "cleanup_artifact":
                status_trigger = "cleanup_status_changed"
            if status_trigger:
                await evaluate_rules(db, status_trigger, context)

        # Commit automation side-effects (notifications, trigger stats)
        await db.commit()
    except Exception as e:
        logger.warning(f"[ActivityLog] Automation engine error (non-fatal): {e}")
        tb.print_exc()
        try:
            await db.rollback()
        except Exception:
            pass

class ConnectionManager:
    def __init__(self):
        # Store active connections: resource_type -> resource_id -> list of websockets
        self.active_connections: Dict[str, Dict[str, List[WebSocket]]] = {}
        # Store active users info: websocket -> user_info
        self.connection_info: Dict[WebSocket, dict] = {}

    async def connect(self, websocket: WebSocket, resource_type: str, resource_id: str, user_info: dict):
        if resource_type not in self.active_connections:
            self.active_connections[resource_type] = {}
        
        if resource_id not in self.active_connections[resource_type]:
            self.active_connections[resource_type][resource_id] = []
        
        # Just add the new connection — old stale connections from the same user
        # are pruned naturally when broadcast fails (in broadcast_to_resource).
        # DO NOT close existing connections here: the close event triggers the
        # client to reconnect, which closes THIS connection, creating an
        # infinite disconnect/reconnect loop.
        self.active_connections[resource_type][resource_id].append(websocket)
        self.connection_info[websocket] = user_info
        
        # Broadcast user joined
        await self.broadcast_to_resource(resource_type, resource_id, {
            "type": "presence_update",
            "action": "joined",
            "user": user_info
        })

    def disconnect(self, websocket: WebSocket, resource_type: str, resource_id: str):
        if resource_type in self.active_connections:
            if resource_id in self.active_connections[resource_type]:
                if websocket in self.active_connections[resource_type][resource_id]:
                    self.active_connections[resource_type][resource_id].remove(websocket)
                    
                    # Clean up empty lists
                    if not self.active_connections[resource_type][resource_id]:
                        del self.active_connections[resource_type][resource_id]
        
        user_info = self.connection_info.pop(websocket, None)
        
        # We can't await here directly if called from a non-async context, 
        # but in FastAPI disconnects are typically handled in the endpoint loop.
        return user_info

    async def broadcast_to_resource(
        self,
        resource_type: str,
        resource_id: str,
        message: dict,
        db: Optional[AsyncSession] = None,
    ):
        if resource_type in self.active_connections:
            if resource_id in self.active_connections[resource_type]:
                # Get current active users for this resource to include in presence updates
                if message.get("type") == "presence_update":
                    # Deduplicate by user ID (a user may have multiple connections)
                    seen_ids = set()
                    active_users = []
                    for ws in self.active_connections[resource_type][resource_id]:
                        info = self.connection_info.get(ws)
                        if info and info.get('id') not in seen_ids:
                            seen_ids.add(info['id'])
                            active_users.append(info)
                    # Sort by user ID for stable ordering (prevents icon flipping)
                    active_users.sort(key=lambda u: u.get('id', ''))
                    message["active_users"] = active_users

                # dashboard:global is the cross-engagement notification stream.
                # Subscribers are any authenticated user; the membership gate
                # has to be applied per-recipient at broadcast time so a
                # subscriber only receives events for engagements they can see.
                # Other channels (engagement:X, dashboard:X, note:X) are scoped
                # at subscribe time and need no per-recipient filter.
                gating_engagement: Optional[str] = None
                if (
                    resource_type == "dashboard"
                    and resource_id == "global"
                    and db is not None
                ):
                    gating_engagement = message.get("engagement_id")

                encoded_message = json.dumps(message)
                dead_connections = []
                for connection in self.active_connections[resource_type][resource_id]:
                    if gating_engagement is not None:
                        info = self.connection_info.get(connection) or {}
                        recipient_id = info.get("id")
                        if not recipient_id:
                            # Fail closed: don't deliver to unidentified connections
                            continue
                        try:
                            from auth.rbac import check_engagement_permission
                            from models.permission import Permission
                            allowed = await check_engagement_permission(
                                recipient_id,
                                gating_engagement,
                                Permission.ENGAGEMENT_VIEW.value,
                                db,
                            )
                        except Exception as e:
                            logger.warning(
                                f"dashboard:global membership check failed for "
                                f"user {recipient_id} on engagement "
                                f"{gating_engagement}: {e}"
                            )
                            allowed = False
                        if not allowed:
                            continue
                    try:
                        await connection.send_text(encoded_message)
                    except:
                        dead_connections.append(connection)
                
                # Prune dead connections
                if dead_connections:
                    for conn in dead_connections:
                        if conn in self.active_connections[resource_type][resource_id]:
                            self.active_connections[resource_type][resource_id].remove(conn)
                        self.connection_info.pop(conn, None)
                    
                    # Clean up empty resource lists
                    if not self.active_connections[resource_type][resource_id]:
                        del self.active_connections[resource_type][resource_id]

manager = ConnectionManager()
