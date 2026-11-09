from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, status
from typing import Optional, Tuple
import asyncio
import json
import time as _time
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


# Y.js binary wire format (see y-protocols).
# Top-level msg type varUint:
#   0 = MSG_SYNC — followed by a sub-type varUint
#   1 = MSG_AWARENESS — cursor / presence updates
# MSG_SYNC sub-types:
#   0 = SyncStep1  — client sends its state vector, "give me what I'm missing"
#   1 = SyncStep2  — server/peer response containing the missing updates
#   2 = Update     — a new document mutation (WRITE)
# Values 0-127 are single-byte varUints, so we can inspect data[0]/data[1].
_YJS_MSG_SYNC = 0
_YJS_MSG_AWARENESS = 1
_YJS_SYNC_STEP1 = 0
_YJS_SYNC_STEP2 = 1
_YJS_SYNC_UPDATE = 2


def _is_viewer_safe_binary(data: bytes) -> bool:
    """True if a binary Y.js message is safe to relay from a read-only
    client — awareness (cursor / presence) or SYNC step 1 (a state-vector
    query). Blocks SYNC step 2 and UPDATE: both carry a document update
    that peers apply, so either would let a viewer inject CRDT writes into
    an editor's live ydoc, which the editor's next autosave persists.

    Rejects a leading zero-length or truncated message (defensive
    against a client dumping empty frames)."""
    if not data:
        return False
    top = data[0]
    if top == _YJS_MSG_AWARENESS:
        return True
    if top == _YJS_MSG_SYNC:
        if len(data) < 2:
            return False
        subtype = data[1]
        return subtype == _YJS_SYNC_STEP1
    return False


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
    # must_change_password: same gate as get_current_user — no live feeds or
    # live-edit saves until the forced change is done.
    if not user_row or not user_row.is_active or user_row.must_change_password:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None

    return user_row, user_row.role.value

def _apply_identify(user_info: dict, claimed) -> None:
    """Apply a presence ``identify`` frame. Only the client's edit/view mode is
    taken: ``id`` and ``role`` gate per-recipient delivery (the
    dashboard:global engagement check reads ``connection_info[ws]["id"]``), so
    a client-supplied ``id`` would let anyone receive another user's feed; the
    display fields are already set from the DB row at connect."""
    if isinstance(claimed, dict) and claimed.get("mode") in ("edit", "view"):
        user_info["mode"] = claimed["mode"]


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

    # 3. Connect to manager. Identity comes from the authenticated DB row;
    # the client's `identify` frame may only set its edit/view mode (see
    # _apply_identify).
    user_info = {
        "id": user_id,
        "role": role,
        "username": user_row.username,
        "full_name": user_row.full_name,
        "profile_photo": user_row.profile_photo,
        "mode": "view",
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
                _apply_identify(user_info, data.get("user"))
                await manager.refresh_presence(websocket, resource_type, resource_id)
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
        await manager.leave(websocket, resource_type, resource_id)
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

# How often an open live-edit socket re-checks the user's access (see
# _serve_yjs_room). Saves always re-check.
_ACCESS_RECHECK_S = 15


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
    from utils.yjs_server import save_note_content

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
    #   - VIEW bypass: admin / read-only-admin / team-lead (three roles).
    #     Previously an admin who wasn't a direct engagement member
    #     couldn't open the Y.js sync socket at all — the WS was a
    #     *stricter* door than the REST fetch, so the note metadata
    #     loaded fine and the collab handshake silently hung.
    #   - WRITE bypass: admin / team-lead only (two roles — no
    #     read-only-admin). read-only-admin passes VIEW but must not
    #     write, matching notes.py:203 and every other REST edit gate.
    #     Previously this treated all three view-bypass roles as edit-
    #     capable, which let read-only-admin save note content and
    #     broadcast CRDT updates even though REST would 403 them.
    can_edit = await _note_access(user_row, note, db)
    if can_edit is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # 3. Join the Y.js room and relay until the client leaves.
    async def _save(content: str):
        await save_note_content(note_id, content, user_id)

    async def _recheck(rdb: AsyncSession, live_user: User) -> Optional[bool]:
        live_note = (await rdb.execute(select(Note).where(Note.id == note_id))).scalar_one_or_none()
        return None if live_note is None else await _note_access(live_user, live_note, rdb)

    await _serve_yjs_room(
        websocket, note_id, user_id, can_edit,
        initial_content=note.content or "", persist=True, on_save=_save,
        extra_initial={"note_id": note_id}, recheck=_recheck,
    )


async def _note_access(user_row: User, note, db: AsyncSession) -> Optional[bool]:
    """None = may not view the note; otherwise whether they may edit it."""
    role = user_row.role.value
    # Mirrors routers/notes.py:
    #   - VIEW bypass: admin / read-only-admin / team-lead (three roles).
    #     Previously an admin who wasn't a direct engagement member
    #     couldn't open the Y.js sync socket at all — the WS was a
    #     *stricter* door than the REST fetch, so the note metadata
    #     loaded fine and the collab handshake silently hung.
    #   - WRITE bypass: admin / team-lead only (two roles — no
    #     read-only-admin). read-only-admin passes VIEW but must not
    #     write, matching notes.py and every other REST edit gate.
    is_admin_view = role in (
        UserRole.ADMIN.value,
        UserRole.READ_ONLY_ADMIN.value,
        UserRole.TEAM_LEAD.value,
    )
    if not is_admin_view and not await check_engagement_permission(
        user_row.id, note.engagement_id, Permission.NOTE_VIEW.value, db
    ):
        return None
    if role in (UserRole.ADMIN.value, UserRole.TEAM_LEAD.value):
        return True
    edit_perm = Permission.NOTE_EDIT.value if note.created_by == user_row.id else Permission.NOTE_EDIT_ANY.value
    return await check_engagement_permission(user_row.id, note.engagement_id, edit_perm, db)


@router.websocket("/ws/yjs/field/{resource_type}/{resource_id}/{field}")
async def yjs_field_websocket_endpoint(
    websocket: WebSocket,
    resource_type: str,
    resource_id: str,
    field: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Y.js sync for one rich-text field of a finding / test case / asset, or a
    report builder text section — live co-editing on the edit pages.

    Same first-frame auth and relay as the note socket. Editors send the
    field's Markdown (``save_content``) after a pause in typing; it's written
    by ``save_collab_field`` and acknowledged with ``content_saved``. See
    utils/collab_fields.py for the field allow-list and permission mapping.
    """
    from utils.collab_fields import resolve_collab_target, room_key, save_collab_field
    import json as _json_mod

    await websocket.accept()
    authed = await _auth_via_first_frame(websocket, db)
    if authed is None:
        return
    user_row, _role = authed

    target = await resolve_collab_target(resource_type, resource_id, field, user_row, db)
    if target is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    async def _save(content: str):
        if not isinstance(content, str):
            return
        ok = await save_collab_field(resource_type, resource_id, field, content, user_row.id)
        try:
            await websocket.send_text(_json_mod.dumps({"type": "content_saved", "ok": ok}))
        except Exception:
            pass

    async def _recheck(rdb: AsyncSession, live_user: User) -> Optional[bool]:
        live = await resolve_collab_target(resource_type, resource_id, field, live_user, rdb)
        return None if live is None else live.can_edit

    # persist=False: no server-initiated save requests — the author's client
    # decides when to send (a viewer could otherwise be asked to save).
    await _serve_yjs_room(
        websocket, room_key(resource_type, resource_id, field), user_row.id, target.can_edit,
        initial_content=target.content, persist=False, on_save=_save, recheck=_recheck,
    )


async def _serve_yjs_room(
    websocket: WebSocket,
    key: str,
    user_id: str,
    can_edit: bool,
    *,
    initial_content: str,
    persist: bool,
    on_save,
    extra_initial: Optional[dict] = None,
    recheck=None,
):
    """Join the Y.js room ``key``, send the bootstrap frame, and relay frames
    until the client disconnects. ``on_save`` handles a client's
    ``save_content`` (editors only); None ignores it.

    ``recheck(db, user) -> None | bool`` re-evaluates access mid-session (None
    = can no longer view, else can_edit), so revoking someone's engagement
    role, deactivating them or demoting them takes effect on an open socket
    instead of at their next connect. It runs before every save, at most
    every ``_ACCESS_RECHECK_S`` on other frames, and on a timer every
    ``_ACCESS_RECHECK_S`` — an idle client sends nothing, so frames alone
    would leave a revoked viewer watching indefinitely. Edit lost →
    the socket becomes read-only (``access_changed``); view lost →
    ``access_revoked`` and close."""
    from utils.yjs_server import yjs_store
    from utils.ws_bus import bus as _bus
    import json as _json
    import uuid as _uuid

    room = yjs_store.get_or_create_room(key, persist=persist)
    await room.add_client(websocket, user_id)
    _yjs_conn = _uuid.uuid4().hex
    await _bus.presence_add("yjs", key, _yjs_conn, {"id": user_id})

    # Start cleanup loop if not running
    yjs_store.start_cleanup_loop()

    # Send initial content as markdown so clients can bootstrap
    # (only used when no peers are connected to sync from). `peers` is the
    # number of OTHER clients already in the room (self is already added), so
    # the client can skip the sync wait and reveal the DB copy immediately when
    # it's alone — and only pay the peer-sync latency when joining an occupied
    # room, where a peer holds the authoritative Y.js doc to sync from.
    try:
        await websocket.send_text(_json.dumps({
            "type": "initial_content",
            "content": initial_content,
            "peers": await _yjs_peer_count(key, room),
            # Lets a read-only client drop its own DB seed once an editor's
            # content arrives (its seed never reaches peers, see below).
            "can_edit": can_edit,
            **(extra_initial or {}),
        }))
    except Exception:
        pass

    last_check = _time.monotonic()

    async def _refresh_access(force: bool) -> bool:
        """Re-check access; False if the socket was closed for lost view."""
        nonlocal can_edit, last_check
        if recheck is None or (not force and _time.monotonic() - last_check < _ACCESS_RECHECK_S):
            return True
        last_check = _time.monotonic()
        try:
            from database import AsyncSessionLocal
            async with AsyncSessionLocal() as rdb:
                live_user = (await rdb.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
                if live_user is None or not live_user.is_active or live_user.must_change_password:
                    allowed = None
                else:
                    allowed = await recheck(rdb, live_user)
        except Exception as e:  # noqa: BLE001
            # Fail closed for writes only: a transient DB error shouldn't
            # kick viewers, but nobody saves on an unverified right.
            logger.warning("yjs access recheck failed for %s on %s: %s", user_id, key, e)
            if can_edit:
                can_edit = False
                await _send_json({"type": "access_changed", "can_edit": False})
            last_check = 0.0  # try again on the next frame
            return True
        if allowed is None:
            await _send_json({"type": "access_revoked"})
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return False
        if allowed != can_edit:
            can_edit = allowed
            await _send_json({"type": "access_changed", "can_edit": can_edit})
        return True

    async def _send_json(payload: dict) -> None:
        try:
            await websocket.send_text(_json.dumps(payload))
        except Exception:
            pass

    async def _recheck_timer() -> None:
        while True:
            await asyncio.sleep(_ACCESS_RECHECK_S or 1)
            if not await _refresh_access(force=True):
                return  # socket closed; the receive loop sees the disconnect

    timer = asyncio.create_task(_recheck_timer()) if recheck is not None else None

    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                raise WebSocketDisconnect(message.get("code", 1000))
            if not await _refresh_access(force=False):
                raise WebSocketDisconnect(status.WS_1008_POLICY_VIOLATION)

            if "bytes" in message and message["bytes"]:
                # Binary Y.js sync/awareness message. Read-only viewers
                # may still emit query messages (Y.js sync step 1 asks
                # peers for their state) and awareness messages (cursor
                # / presence). Without step 1 going through, a read-only
                # viewer never bootstraps from active peers — they see
                # the DB snapshot from initial_content and then diverge
                # from live edits. Step 2 and UPDATE both carry document
                # content, so a viewer's are dropped: relayed, an editor
                # would merge them and its next save_content would
                # persist the viewer's text.
                if can_edit or _is_viewer_safe_binary(message["bytes"]):
                    await room.relay_binary(websocket, message["bytes"])

            elif "text" in message and message["text"]:
                # JSON control message (save_content, register_client_id)
                try:
                    data = _json.loads(message["text"])

                    if data.get("type") == "save_content":
                        if on_save is None:
                            continue
                        if not await _refresh_access(force=True):
                            raise WebSocketDisconnect(status.WS_1008_POLICY_VIOLATION)
                        if not can_edit:
                            # Tell the client, so it stops showing "Saving…".
                            await _send_json({"type": "content_saved", "ok": False})
                            continue
                        await on_save(data.get("content", ""))
                    elif data.get("type") == "register_client_id":
                        # Client tells us its Y.js clientID so we can notify
                        # peers when it disconnects (for cursor cleanup)
                        yjs_id = data.get("client_id")
                        if yjs_id is not None:
                            room.set_client_yjs_id(websocket, int(yjs_id))

                except (_json.JSONDecodeError, TypeError, ValueError):
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
    finally:
        if timer is not None:
            timer.cancel()
        await _bus.presence_remove("yjs", key, _yjs_conn)


async def _yjs_peer_count(note_id: str, room) -> int:
    """Other clients editing this note on any worker (self already counted)."""
    from utils.ws_bus import bus
    members = await bus.presence_list("yjs", note_id)
    total = len(members) if members is not None else len(room.clients)
    return max(0, total - 1)
