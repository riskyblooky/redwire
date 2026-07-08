from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, status
from typing import Optional, Tuple
import asyncio
import json
import logging
from utils.collaboration import manager
from auth import decode_token
from auth.jwt import is_token_blacklisted
from auth.rbac import check_engagement_permission
from models.permission import Permission
from database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

logger = logging.getLogger(__name__)
from models.user import User, UserRole
import logging

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


# Window the client has to send the auth frame after `accept()`. Generous
# enough that a slow mobile network can land it without retry, tight
# enough that a no-frame opportunistic connection doesn't sit on a
# manager slot indefinitely.
_AUTH_FRAME_TIMEOUT_S = 5.0


async def _auth_via_first_frame(
    websocket: WebSocket,
    db: AsyncSession,
) -> Optional[Tuple[User, str]]:
    """Pull the auth bearer out of the first JSON frame after ``accept()``.

    Replaces the prior ``?token=`` query-param model. Putting the bearer
    in the URL leaked the JWT to anywhere the URL appeared — browser
    history, nginx access logs, Referer headers on subresource fetches,
    process listings on CLI clients (CWE-598). The first-frame shape
    keeps the credential inside the WebSocket payload so none of those
    sinks see it.

    Expected frame shape: ``{"type": "auth", "token": "<access-jwt>"}``.

    Returns ``(user, role_value)`` on success. Returns ``None`` AND
    closes the socket with 1008 on:
      - timeout (client never sent a frame)
      - malformed / non-JSON frame
      - wrong frame type or missing token field
      - invalid / blacklisted / 2FA-pending JWT
      - user not found or inactive

    The handler should treat a ``None`` return as "auth failed, the
    socket is already closed, return."
    """
    try:
        raw = await asyncio.wait_for(
            websocket.receive_text(), timeout=_AUTH_FRAME_TIMEOUT_S
        )
    except asyncio.TimeoutError:
        logger.debug("WS auth: no frame within %ss; closing", _AUTH_FRAME_TIMEOUT_S)
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None
    except WebSocketDisconnect:
        return None

    try:
        frame = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None

    if not isinstance(frame, dict) or frame.get("type") != "auth":
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None

    token = frame.get("token")
    if not isinstance(token, str) or not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None

    payload = decode_token(token)
    if not payload:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None

    # Reject non-access tokens (refresh / password_reset / etc.) — REST
    # dependency does the same; WS must not be a softer door.
    if payload.get("type") != "access":
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None

    # Reject revoked or 2FA-pending tokens
    if is_token_blacklisted(token) or payload.get("2fa_pending"):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None

    user_id = payload.get("sub")
    if not user_id:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None

    # Load the User row so role and is_active reflect the live DB state,
    # not whatever the JWT was minted with. Without this, a freshly
    # deactivated or demoted user keeps WS access until their access
    # token naturally expires. GHSA-464j-7qr3-47pj.
    user_row = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if not user_row or not user_row.is_active:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None

    return user_row, user_row.role.value

@router.websocket("/ws/{resource_type}/{resource_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    resource_type: str,
    resource_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    WebSocket endpoint for real-time collaboration.
    Accepts first, then authenticates via a first-message auth frame
    (NOT a ?token=... query param — that put the bearer JWT in URLs
    captured by browser history / nginx logs / Referer headers, CWE-598).
    Client must send {"type": "auth", "token": "<access-jwt>"} within
    ``_AUTH_FRAME_TIMEOUT_S`` of the accept().
    """
    await websocket.accept()

    # 1. Authenticate via first-frame
    authed = await _auth_via_first_frame(websocket, db)
    if authed is None:
        return  # helper already closed the socket
    user_row, role = authed
    user_id = user_row.id

    # 2. Resolve resource and capture its owning engagement_id (where applicable).
    from models.engagement import Engagement
    from models.finding import Finding

    resource_exists = False
    engagement_id: Optional[str] = None
    try:
        from models.asset import Asset
        from models.testcase import TestCase
        from models.evidence import Evidence

        if resource_type == "engagement":
            result = await db.execute(select(Engagement).where(Engagement.id == resource_id))
            obj = result.scalar_one_or_none()
            resource_exists = obj is not None
            engagement_id = obj.id if obj else None
        elif resource_type == "finding":
            result = await db.execute(select(Finding).where(Finding.id == resource_id))
            obj = result.scalar_one_or_none()
            resource_exists = obj is not None
            engagement_id = getattr(obj, "engagement_id", None) if obj else None
        elif resource_type == "asset":
            result = await db.execute(select(Asset).where(Asset.id == resource_id))
            obj = result.scalar_one_or_none()
            resource_exists = obj is not None
            engagement_id = getattr(obj, "engagement_id", None) if obj else None
        elif resource_type == "testcase":
            result = await db.execute(select(TestCase).where(TestCase.id == resource_id))
            obj = result.scalar_one_or_none()
            resource_exists = obj is not None
            engagement_id = getattr(obj, "engagement_id", None) if obj else None
        elif resource_type == "evidence":
            result = await db.execute(select(Evidence).where(Evidence.id == resource_id))
            obj = result.scalar_one_or_none()
            resource_exists = obj is not None
            engagement_id = getattr(obj, "engagement_id", None) if obj else None
        elif resource_type == "note":
            from models.note import Note
            result = await db.execute(select(Note).where(Note.id == resource_id))
            obj = result.scalar_one_or_none()
            resource_exists = obj is not None
            engagement_id = getattr(obj, "engagement_id", None) if obj else None
        elif resource_type == "report":
            # Reports are virtual resources linked to engagement
            result = await db.execute(select(Engagement).where(Engagement.id == resource_id))
            obj = result.scalar_one_or_none()
            resource_exists = obj is not None
            engagement_id = obj.id if obj else None
        elif resource_type == "dashboard":
            # Dashboard is a virtual global resource — broadcast-only.
            resource_exists = resource_id == "global"
        elif resource_type == "user":
            # User-level notification channel
            result = await db.execute(select(User).where(User.id == resource_id))
            resource_exists = result.scalar_one_or_none() is not None
        else:
            resource_exists = False
    except Exception as e:
        print(f"WS Resource validation error: {e}")
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        return

    if not resource_exists:
        await websocket.close(code=status.WS_1003_UNSUPPORTED_DATA)
        return

    # 2b. user channel: caller may only subscribe to their OWN id.
    if resource_type == "user" and str(resource_id) != str(user_id):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # 2c. Engagement-scoped resources: require ENGAGEMENT_VIEW on the owning
    # engagement. (dashboard:global is intentionally permissive here;
    # broadcast-side scoping is tracked separately.)
    #
    # Admin / read-only-admin / team-lead bypass the per-engagement
    # gate — same pattern as every REST view endpoint (see e.g.
    # engagements.py:323, notes.py:121). Without this an admin who
    # isn't a direct member of the engagement can't open the
    # collaboration WS at all, so /notes and every other real-time
    # surface silently 1008-close for them.
    if engagement_id is not None:
        is_admin_view = role in (
            UserRole.ADMIN.value,
            UserRole.READ_ONLY_ADMIN.value,
            UserRole.TEAM_LEAD.value,
        )
        if not is_admin_view and not await check_engagement_permission(
            user_id, engagement_id, Permission.ENGAGEMENT_VIEW.value, db
        ):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    # 3. Connect to manager
    user_info = {
        "id": user_id,
        "role": role,
    }
    await manager.connect(websocket, resource_type, resource_id, user_info)

    # GHSA-c96m-c63f-3f2c: route cleanup through `finally` so the slot is
    # released on every exit path — clean disconnect, malformed frame,
    # wrong frame type, mid-message client abort, task cancellation. Per-
    # frame JSON parse errors no longer tear the whole connection down;
    # the loop continues so a buggy client doesn't get an immediate kick.
    try:
        while True:
            try:
                data = await websocket.receive_json()
            except (json.JSONDecodeError, ValueError):
                # Bad frame — log + continue so the presence slot survives.
                logger.debug(
                    "presence WS %s/%s: ignoring malformed frame from user %s",
                    resource_type, resource_id, user_id,
                )
                continue

            # Handle client messages
            if data.get("type") == "identify":
                # Update user info with name/etc provided by client
                user_info.update(data.get("user", {}))
                # Broadcast the update to all users
                await manager.broadcast_to_resource(resource_type, resource_id, {
                    "type": "presence_update",
                    "action": "identified",
                    "user": user_info
                })

            elif data.get("type") == "cursor_move":
                # Broadcast cursor to others
                await manager.broadcast_to_resource(resource_type, resource_id, {
                    "type": "cursor_update",
                    "user_id": user_id,
                    "position": data.get("position")
                })

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        # Any other exception (e.g. binary frame → RuntimeError, network
        # reset mid-frame) — log and fall through to cleanup. The previous
        # bare `except WebSocketDisconnect` let these leak the slot.
        logger.warning(
            "presence WS %s/%s for user %s closed on %s: %s",
            resource_type, resource_id, user_id, type(exc).__name__, exc,
        )
    finally:
        manager.disconnect(websocket, resource_type, resource_id)
        try:
            await manager.broadcast_to_resource(resource_type, resource_id, {
                "type": "presence_update",
                "action": "left",
                "user_id": user_id
            })
        except Exception as exc:
            # Best-effort departure broadcast — never surface from cleanup.
            logger.debug(
                "presence WS %s/%s: 'left' broadcast for user %s failed: %s",
                resource_type, resource_id, user_id, exc,
            )


# ─── Y.js Collaborative Editing WebSocket ────────────────────────────

@router.websocket("/ws/yjs/note/{note_id}")
async def yjs_websocket_endpoint(
    websocket: WebSocket,
    note_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Y.js binary sync WebSocket for collaborative note editing.

    Authenticates via a first-message JSON auth frame
    ({"type":"auth","token":"<access-jwt>"}). Bearer must NOT appear in
    the connect URL — CWE-598. Binary Y.js sync frames flow on every
    subsequent message.

    Handles both binary Y.js sync protocol messages and JSON control
    messages (save responses, awareness updates).
    """
    from utils.yjs_server import yjs_store, save_note_content
    import json as _json

    await websocket.accept()

    # 1. Authenticate via first-frame
    authed = await _auth_via_first_frame(websocket, db)
    if authed is None:
        return  # helper already closed the socket
    user_row, role = authed
    user_id = user_row.id

    # 2. Verify note exists
    from models.note import Note
    result = await db.execute(select(Note).where(Note.id == note_id))
    note = result.scalar_one_or_none()
    if not note:
        await websocket.close(code=status.WS_1003_UNSUPPORTED_DATA)
        return

    # 2b. Authorize against the note's engagement. Mirrors routers/notes.py:
    #   - view requires NOTE_VIEW
    #   - edit requires NOTE_EDIT (owner) or NOTE_EDIT_ANY (non-owner);
    #     admin / read-only-admin / team-lead bypass the edit check
    # Without this, the WS path is a softer door than the REST one.
    #
    # Admin / read-only-admin / team-lead bypass the VIEW gate too
    # (mirrors notes.py:121). Previously an admin who wasn't a direct
    # engagement member couldn't open the Y.js sync socket for any
    # note in that engagement — the WS was a *stricter* door than
    # the REST fetch of the same note, so the frontend loaded the
    # note metadata fine and then hung on the collab handshake.
    is_admin = role in (
        UserRole.ADMIN.value,
        UserRole.READ_ONLY_ADMIN.value,
        UserRole.TEAM_LEAD.value,
    )
    if not is_admin and not await check_engagement_permission(
        user_id, note.engagement_id, Permission.NOTE_VIEW.value, db
    ):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    if is_admin:
        can_edit = True
    else:
        is_owner = note.created_by == user_id
        edit_perm = (
            Permission.NOTE_EDIT.value if is_owner else Permission.NOTE_EDIT_ANY.value
        )
        can_edit = await check_engagement_permission(
            user_id, note.engagement_id, edit_perm, db
        )

    # 3. Join the Y.js room
    room = yjs_store.get_or_create_room(note_id)
    await room.add_client(websocket, user_id)

    # Start cleanup loop if not running
    yjs_store.start_cleanup_loop()

    # Send initial content as markdown so clients can bootstrap
    # (only used when no peers are connected to sync from)
    initial_content = note.content or ""
    try:
        await websocket.send_text(_json.dumps({
            "type": "initial_content",
            "content": initial_content,
            "note_id": note_id,
        }))
    except Exception:
        pass

    try:
        while True:
            message = await websocket.receive()

            if "bytes" in message and message["bytes"]:
                # Binary Y.js sync/awareness message — relay to other clients.
                # Read-only viewers cannot broadcast CRDT updates.
                if can_edit:
                    await room.relay_binary(websocket, message["bytes"])

            elif "text" in message and message["text"]:
                # JSON control message (save_content, register_client_id)
                try:
                    data = _json.loads(message["text"])

                    if data.get("type") == "save_content":
                        if not can_edit:
                            continue
                        content = data.get("content", "")
                        await save_note_content(note_id, content, user_id)
                    elif data.get("type") == "register_client_id":
                        # Client tells us its Y.js clientID so we can notify
                        # peers when it disconnects (for cursor cleanup)
                        yjs_id = data.get("client_id")
                        if yjs_id is not None:
                            room.set_client_yjs_id(websocket, int(yjs_id))

                except _json.JSONDecodeError:
                    pass

    except WebSocketDisconnect:
        yjs_id = room.remove_client(websocket)
        # Notify remaining peers to remove this client's awareness/cursor
        if yjs_id is not None:
            await room.notify_peer_disconnected(yjs_id)
        # If room is empty, schedule a final save
        if room.is_empty:
            room._schedule_save()
    except Exception as e:
        logger.warning(f"Y.js WS error: {e}")
        yjs_id = room.remove_client(websocket)
        if yjs_id is not None:
            await room.notify_peer_disconnected(yjs_id)

