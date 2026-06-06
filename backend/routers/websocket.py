from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query, status
from typing import Optional
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

async def get_ws_user(
    websocket: WebSocket,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    """
    Authenticate WebSocket connection via Query param.
    WebSockets don't share HTTP headers easily in JS API.
    """
    try:
        payload = decode_token(token)
        if not payload:
            return None

        # Reject non-access tokens (refresh / password_reset / etc.) so the
        # WS path can't accept JWTs the REST dependency rejects.
        if payload.get("type") != "access":
            return None

        # Reject revoked or 2FA-pending tokens
        if is_token_blacklisted(token):
            return None
        if payload.get("2fa_pending"):
            return None

        user_id = payload.get("sub")
        if not user_id:
            return None
            
        # We need a new session context for WS potentially, or just quick check
        # For simplicity in this demo, we trust the token if valid signature
        # But let's verify user exists really quick
        
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        
        if user and user.is_active:
            return user
        return None
    except Exception:
        return None

@router.websocket("/ws/{resource_type}/{resource_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    resource_type: str,
    resource_id: str,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """
    WebSocket endpoint for real-time collaboration.
    Accepts first, then authenticates to avoid proxy timeout/handshake errors.
    """
    await websocket.accept()

    # 1. Authenticate
    payload = decode_token(token)
    if not payload:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Reject non-access tokens (refresh / password_reset / etc.) — the REST
    # dependency does the same; WS must not be a softer door.
    if payload.get("type") != "access":
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Reject revoked or 2FA-pending tokens
    if is_token_blacklisted(token) or payload.get("2fa_pending"):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    user_id = payload.get("sub")

    # Load the User row so role and is_active reflect the live DB state,
    # not whatever the JWT was minted with. Without this, a freshly
    # deactivated or demoted user keeps WS access until their access
    # token naturally expires. GHSA-464j-7qr3-47pj.
    user_row = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user_row or not user_row.is_active:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    role = user_row.role.value

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
    if engagement_id is not None:
        if not await check_engagement_permission(
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
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Y.js binary sync WebSocket for collaborative note editing.
    
    Handles both binary Y.js sync protocol messages and JSON control
    messages (save responses, awareness updates).
    """
    from utils.yjs_server import yjs_store, save_note_content
    import json as _json

    await websocket.accept()

    # 1. Authenticate
    payload = decode_token(token)
    if not payload:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Reject non-access tokens (refresh / password_reset / etc.) so the WS
    # path can't accept JWTs the REST dependency rejects.
    if payload.get("type") != "access":
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Reject revoked or 2FA-pending tokens
    if is_token_blacklisted(token) or payload.get("2fa_pending"):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    user_id = payload.get("sub")

    # Load the User row so role and is_active reflect the live DB state,
    # not whatever the JWT was minted with. Without this, a demoted user
    # keeps the is_admin = role in (ADMIN, ...) bypass below until their
    # token expires. GHSA-464j-7qr3-47pj.
    user_row = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user_row or not user_row.is_active:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    role = user_row.role.value

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
    if not await check_engagement_permission(
        user_id, note.engagement_id, Permission.NOTE_VIEW.value, db
    ):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    is_admin = role in (
        UserRole.ADMIN.value,
        UserRole.READ_ONLY_ADMIN.value,
        UserRole.TEAM_LEAD.value,
    )
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

