from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query, status
from typing import Optional
from utils.collaboration import manager
from auth import decode_token
from auth.jwt import is_token_blacklisted
from database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.user import User
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

    # Reject revoked or 2FA-pending tokens
    if is_token_blacklisted(token) or payload.get("2fa_pending"):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
        
    user_id = payload.get("sub")
    role = payload.get("role")
    
    # 2. Verify Resource Existence (Security & Validation)
    from models.engagement import Engagement
    from models.finding import Finding
    
    resource_exists = False
    try:
        from models.asset import Asset
        from models.testcase import TestCase
        from models.evidence import Evidence

        if resource_type == "engagement":
            result = await db.execute(select(Engagement).where(Engagement.id == resource_id))
            resource_exists = result.scalar_one_or_none() is not None
        elif resource_type == "finding":
            result = await db.execute(select(Finding).where(Finding.id == resource_id))
            resource_exists = result.scalar_one_or_none() is not None
        elif resource_type == "asset":
            result = await db.execute(select(Asset).where(Asset.id == resource_id))
            resource_exists = result.scalar_one_or_none() is not None
        elif resource_type == "testcase":
            result = await db.execute(select(TestCase).where(TestCase.id == resource_id))
            resource_exists = result.scalar_one_or_none() is not None
        elif resource_type == "evidence":
            result = await db.execute(select(Evidence).where(Evidence.id == resource_id))
            resource_exists = result.scalar_one_or_none() is not None
        elif resource_type == "note":
            from models.note import Note
            result = await db.execute(select(Note).where(Note.id == resource_id))
            resource_exists = result.scalar_one_or_none() is not None
        elif resource_type == "report":
            # Reports are virtual resources linked to engagement
            result = await db.execute(select(Engagement).where(Engagement.id == resource_id))
            resource_exists = result.scalar_one_or_none() is not None
        elif resource_type == "dashboard":
            # Dashboard is a virtual global resource
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

    # 3. Connect to manager
    user_info = {
        "id": user_id,
        "role": role,
    }
    await manager.connect(websocket, resource_type, resource_id, user_info)
    
    try:
        while True:
            data = await websocket.receive_json()
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
        manager.disconnect(websocket, resource_type, resource_id)
        await manager.broadcast_to_resource(resource_type, resource_id, {
            "type": "presence_update",
            "action": "left",
            "user_id": user_id
        })


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

    # Reject revoked or 2FA-pending tokens
    if is_token_blacklisted(token) or payload.get("2fa_pending"):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    user_id = payload.get("sub")
    role = payload.get("role")

    # 2. Verify note exists
    from models.note import Note
    result = await db.execute(select(Note).where(Note.id == note_id))
    note = result.scalar_one_or_none()
    if not note:
        await websocket.close(code=status.WS_1003_UNSUPPORTED_DATA)
        return

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
                # Binary Y.js sync/awareness message — relay to other clients
                await room.relay_binary(websocket, message["bytes"])

            elif "text" in message and message["text"]:
                # JSON control message (save_content, register_client_id)
                try:
                    data = _json.loads(message["text"])

                    if data.get("type") == "save_content":
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

