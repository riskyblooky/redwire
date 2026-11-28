from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from typing import Optional, Tuple
import asyncio
import contextlib
import importlib
import json
import time as _time
import logging
from utils.collaboration import manager
from auth import decode_token
from auth.jwt import is_token_blacklisted
from auth.rbac import check_engagement_permission
from models.permission import Permission
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.user import User, UserRole
# Looked up as database.AsyncSessionLocal at call time (tests patch it).
import database as _database

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
    if payload.get("2fa_pending") or await asyncio.to_thread(is_token_blacklisted, token):
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


async def _engagement_view_allowed(user_row: User, engagement_id: str, db: AsyncSession) -> bool:
    """The presence socket's view gate for an engagement-scoped resource.

    Admin / read-only-admin / team-lead bypass the per-engagement gate, the
    same pattern as every REST view endpoint; without it an admin who isn't
    a direct member couldn't open the collaboration WS at all."""
    role = getattr(user_row.role, "value", user_row.role)
    if role in (UserRole.ADMIN.value, UserRole.READ_ONLY_ADMIN.value, UserRole.TEAM_LEAD.value):
        return True
    return await check_engagement_permission(user_row.id, engagement_id, Permission.ENGAGEMENT_VIEW.value, db)


@contextlib.asynccontextmanager
async def _accepted_and_authenticated(websocket: WebSocket):
    """Accept, open the setup-only DB session and read the first-frame auth.
    Yields ``(db, authed)``: ``authed`` is ``(user_row, role)``, or None
    once ``_auth_via_first_frame`` has closed the socket. The session closes
    when the block ends, before the endpoint's receive loop — an injected
    get_db session lived as long as the socket, pinning a pooled connection
    per open tab (pool: 10 + 20 overflow per worker)."""
    await websocket.accept()
    async with _database.AsyncSessionLocal() as db:
        yield db, await _auth_via_first_frame(websocket, db)


async def _live_user(db: AsyncSession, user_id: str) -> Optional[User]:
    """The user as they are now, or None once they may no longer hold an
    open socket (gone, deactivated, or a forced password change pending)."""
    live = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if live is None or not live.is_active or live.must_change_password:
        return None
    return live


# Resource types the presence socket resolves to a row: the model, and
# whether the row *is* the engagement (else its engagement_id is the owner).
# "report" is a virtual resource on its engagement.
_PRESENCE_MODELS = {
    "engagement": ("models.engagement", "Engagement", True),
    "report": ("models.engagement", "Engagement", True),
    "finding": ("models.finding", "Finding", False),
    "asset": ("models.asset", "Asset", False),
    "testcase": ("models.testcase", "TestCase", False),
    "evidence": ("models.evidence", "Evidence", False),
    "note": ("models.note", "Note", False),
}


async def _resolve_presence_resource(resource_type: str, resource_id: str,
                                     db: AsyncSession) -> tuple[bool, Optional[str]]:
    """``(exists, owning engagement_id)`` for a presence-socket resource.
    ``dashboard`` is a virtual global resource (broadcast-only) and ``user``
    a user's own notification channel; neither is engagement-scoped."""
    if resource_type == "dashboard":
        return resource_id == "global", None
    if resource_type == "user":
        found = (await db.execute(select(User.id).where(User.id == resource_id))).first()
        return found is not None, None
    spec = _PRESENCE_MODELS.get(resource_type)
    if spec is None:
        return False, None
    module, name, is_engagement = spec
    model = getattr(importlib.import_module(module), name)
    obj = (await db.execute(select(model).where(model.id == resource_id))).scalar_one_or_none()
    if obj is None:
        return False, None
    return True, (obj.id if is_engagement else getattr(obj, "engagement_id", None))


def _content_saved_replier(websocket: WebSocket, save):
    """``on_save`` for a Y.js room: persist with ``save(content)`` (-> bool)
    and acknowledge with ``content_saved`` — the shared editor shows
    Saving… / Saved / Not saved from it."""
    async def _on_save(content: str):
        if not isinstance(content, str):
            return
        ok = await save(content)
        try:
            await websocket.send_text(json.dumps({"type": "content_saved", "ok": ok}))
        except Exception:
            pass
    return _on_save


async def _presence_still_allowed(user_id: str, engagement_id: Optional[str]) -> bool:
    """Whether an open presence socket's user may still have it: active, no
    forced password change pending, and (engagement-scoped) still able to
    view the engagement. Uses a fresh session, like the live-edit recheck."""
    async with _database.AsyncSessionLocal() as rdb:
        live = await _live_user(rdb, user_id)
        if live is None:
            return False
        if engagement_id is None:
            return True
        return await _engagement_view_allowed(live, engagement_id, rdb)


async def _presence_recheck_loop(websocket: WebSocket, user_id: str, engagement_id: Optional[str]) -> None:
    """Every ``_ACCESS_RECHECK_S``, close the socket (1008) once its user may
    no longer have it. A transient DB error keeps the socket (fail open for
    a receive-only channel; the next tick retries)."""
    while True:
        await asyncio.sleep(_ACCESS_RECHECK_S or 1)
        try:
            if await _presence_still_allowed(user_id, engagement_id):
                continue
        except Exception as e:  # noqa: BLE001
            logger.warning("presence access recheck failed for %s: %s", user_id, e)
            continue
        try:
            await websocket.send_json({"type": "access_revoked"})
        except Exception:
            pass
        try:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        except Exception:
            pass
        return


@router.websocket("/ws/{resource_type}/{resource_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    resource_type: str,
    resource_id: str,
):
    """
    WebSocket endpoint for real-time collaboration.
    Accepts first, then authenticates via a first-message auth frame
    (NOT a ?token=... query param — that put the bearer JWT in URLs
    captured by browser history / nginx logs / Referer headers, CWE-598).
    Client must send {"type": "auth", "token": "<access-jwt>"} within
    ``_AUTH_FRAME_TIMEOUT_S`` of the accept().
    """
    async with _accepted_and_authenticated(websocket) as (db, authed):
        # 1. Authenticate via first-frame
        if authed is None:
            return  # helper already closed the socket
        user_row, role = authed
        user_id = user_row.id

        # 2. Resolve the resource and its owning engagement (where applicable).
        try:
            resource_exists, engagement_id = await _resolve_presence_resource(resource_type, resource_id, db)
        except Exception as e:
            logger.warning("presence WS %s/%s: resource lookup failed: %s", resource_type, resource_id, e)
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
        if engagement_id is not None and not await _engagement_view_allowed(user_row, engagement_id, db):
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
    # Access is re-checked while the socket is open, as the live-edit sockets
    # do: a deactivated user, or one removed from the engagement, otherwise
    # kept receiving its events until they closed the tab.
    recheck_task = asyncio.create_task(_presence_recheck_loop(websocket, user_id, engagement_id))

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
        recheck_task.cancel()
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

# One access check per (user, record) per interval, shared by that user's
# sockets on the record — an edit page opens one socket per rich-text field,
# and each used to run the same 3-4 queries on its own timer. Worker-local:
# a result is never older than _ACCESS_RECHECK_S, the same bound each socket
# had before, so a revocation still lands within one interval everywhere.
# Saves bypass it (fresh=True).
_access_cache: dict[tuple[str, str], tuple[float, Optional[bool]]] = {}
_access_inflight: dict[tuple[str, str], "asyncio.Future"] = {}


async def _run_access_check(user_id: str, recheck) -> Optional[bool]:
    async with _database.AsyncSessionLocal() as rdb:
        live_user = await _live_user(rdb, user_id)
        return None if live_user is None else await recheck(rdb, live_user)


async def _shared_access_check(cache_key: tuple[str, str], user_id: str, recheck, fresh: bool) -> Optional[bool]:
    """``recheck``'s answer for ``cache_key``: a cached one younger than
    _ACCESS_RECHECK_S, else the in-flight check's, else a new check (always
    a new one when ``fresh``). Errors propagate and aren't cached."""
    if not fresh:
        hit = _access_cache.get(cache_key)
        if hit is not None and _time.monotonic() - hit[0] < _ACCESS_RECHECK_S:
            return hit[1]
        pending = _access_inflight.get(cache_key)
        if pending is not None:
            return await asyncio.shield(pending)
    task = asyncio.ensure_future(_run_access_check(user_id, recheck))
    _access_inflight[cache_key] = task
    try:
        # shield: a socket closing mid-check mustn't cancel the others' wait.
        allowed = await asyncio.shield(task)
    finally:
        if _access_inflight.get(cache_key) is task:
            del _access_inflight[cache_key]
    now = _time.monotonic()
    _access_cache[cache_key] = (now, allowed)
    if len(_access_cache) > 1024:
        for k, (ts, _v) in list(_access_cache.items()):
            if now - ts >= _ACCESS_RECHECK_S:
                del _access_cache[k]
    return allowed


@router.websocket("/ws/yjs/note/{note_id}")
async def yjs_websocket_endpoint(
    websocket: WebSocket,
    note_id: str,
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

    async with _accepted_and_authenticated(websocket) as (db, authed):
        # 1. Authenticate via first-frame
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
    _save = _content_saved_replier(websocket, lambda content: save_note_content(note_id, content, user_id))

    async def _recheck(rdb: AsyncSession, live_user: User) -> Optional[bool]:
        live_note = (await rdb.execute(select(Note).where(Note.id == note_id))).scalar_one_or_none()
        return None if live_note is None else await _note_access(live_user, live_note, rdb)

    await _serve_yjs_room(
        websocket, note_id, user_id, can_edit,
        initial_content=note.content or "", persist=True, on_save=_save,
        extra_initial={"note_id": note_id}, recheck=_recheck, share_key=f"note:{note_id}",
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

    async with _accepted_and_authenticated(websocket) as (db, authed):
        if authed is None:
            return
        user_row, _role = authed

        target = await resolve_collab_target(resource_type, resource_id, field, user_row, db)
        if target is None:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    _save = _content_saved_replier(
        websocket, lambda content: save_collab_field(resource_type, resource_id, field, content, user_row.id))

    async def _recheck(rdb: AsyncSession, live_user: User) -> Optional[bool]:
        live = await resolve_collab_target(resource_type, resource_id, field, live_user, rdb)
        return None if live is None else live.can_edit

    # persist=False: no server-initiated save requests — the author's client
    # decides when to send (a viewer could otherwise be asked to save).
    await _serve_yjs_room(
        websocket, room_key(resource_type, resource_id, field), user_row.id, target.can_edit,
        initial_content=target.content, persist=False, on_save=_save, recheck=_recheck,
        # Access is per record, not per field: the page's field sockets share it.
        share_key=f"{resource_type}:{resource_id}",
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
    share_key: Optional[str] = None,
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
    ``access_revoked`` and close. The timer and frame checks share one
    result per (user, ``share_key``) per interval (``_shared_access_check``);
    a save always checks afresh."""
    from utils.yjs_server import yjs_store
    from utils.ws_bus import bus as _bus
    import json as _json
    import uuid as _uuid

    room = yjs_store.get_or_create_room(key, persist=persist)
    await room.add_client(websocket, user_id)
    _yjs_conn = _uuid.uuid4().hex
    # tab + can_edit let the version-restore guard skip read-only viewers and
    # the restoring tab's own editors (utils/collab_fields.py).
    _qp = getattr(websocket, "query_params", None)
    _tab = ((_qp.get("tab") if _qp is not None else None) or "")[:64]

    async def _publish_presence() -> None:
        await _bus.presence_add("yjs", key, _yjs_conn, {"id": user_id, "tab": _tab, "can_edit": bool(can_edit)})
    await _publish_presence()

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

    cache_key = (user_id, share_key or key)

    async def _refresh_access(force: bool, fresh: bool = False) -> bool:
        """Re-check access; False if the socket was closed for lost view."""
        nonlocal can_edit, last_check
        if recheck is None or (not force and _time.monotonic() - last_check < _ACCESS_RECHECK_S):
            return True
        last_check = _time.monotonic()
        try:
            allowed = await _shared_access_check(cache_key, user_id, recheck, fresh)
        except Exception as e:  # noqa: BLE001
            # Fail closed for writes only: a transient DB error shouldn't
            # kick viewers, but nobody saves on an unverified right.
            logger.warning("yjs access recheck failed for %s on %s: %s", user_id, key, e)
            if can_edit:
                can_edit = False
                await _send_json({"type": "access_changed", "can_edit": False})
                await _publish_presence()
            last_check = 0.0  # try again on the next frame
            return True
        if allowed is None:
            await _send_json({"type": "access_revoked"})
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return False
        if allowed != can_edit:
            can_edit = allowed
            await _send_json({"type": "access_changed", "can_edit": can_edit})
            await _publish_presence()
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
                viewer_safe = _is_viewer_safe_binary(message["bytes"])
                if can_edit or viewer_safe:
                    await room.relay_binary(websocket, message["bytes"], carries_update=not viewer_safe)

            elif "text" in message and message["text"]:
                # JSON control message (save_content, register_client_id)
                try:
                    data = _json.loads(message["text"])

                    if data.get("type") == "save_content":
                        if on_save is None:
                            continue
                        if not await _refresh_access(force=True, fresh=True):
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
    # This worker's own clients are certain; the registry can briefly lag
    # them (e.g. until the next heartbeat re-asserts a failed add).
    total = max(len(members), len(room.clients)) if members is not None else len(room.clients)
    return max(0, total - 1)
