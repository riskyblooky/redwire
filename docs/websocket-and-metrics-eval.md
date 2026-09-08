# WebSocket & Effort-Metrics Evaluation

_Site-wide probe into where server-side WebSocket push helps, and how to derive
effort/time-on-task metrics ("time spent writing findings" and similar)._

Status: evaluation + plan. Findings current as of the 1.5.6 cycle.

---

## 0. TL;DR

- A capable WS layer already exists; **most list pages are already live** via the
  `activity_log` firehose. Don't rebuild it.
- **The governing constraint:** the connection manager is an in-memory dict and
  prod runs a **single uvicorn worker / single replica**. WS push works *only*
  because everything shares one process. Redis is a dependency but is **not** a
  WS broker. Scaling to `--workers >1` or multiple replicas silently fragments
  all push. Fix (Redis pub/sub fan-out) is the precondition for scaling — not
  urgent, but know it.
- **Quick WS wins** (gaps 1–5 below): detail pages, the analytics page, and
  infrastructure aren't live; the admin user list polls; a couple of fallback
  polls are redundant.
- **Effort metrics:** the raw signals are too coarse for findings/testcases
  (one activity-log row per Save). The accurate path is a small **append-only
  "activity ping"** stream that reuses the heartbeat's client gating but adds
  *which resource is open* — it powers both time-on-task metrics and a richer
  "actively editing" presence, and needs **no** WS/scaling work (it's a POST).

---

## 1. Current WebSocket architecture

Two endpoints (`backend/routers/websocket.py`):

- **Generic presence/broadcast** — `/ws/{resource_type}/{resource_id}` for
  `engagement`, `finding`, `asset`, `testcase`, `evidence`, `note`, `report`,
  `dashboard/global`, `dashboard/{engagement_id}`, `user/{id}`. JSON only.
- **Yjs CRDT** — `/ws/yjs/note/{note_id}` (binary), via `utils/yjs_server.py`.

**Manager:** `ConnectionManager` singleton (`utils/collaboration.py`), in-memory
`active_connections[resource_type][resource_id] -> [WebSocket]`; one broadcast
primitive `broadcast_to_resource(...)`. Yjs uses a separate in-memory
`yjs_store`.

**Auth:** first-frame JWT (`{"type":"auth","token":...}`, no `?token=`), live
`User` lookup, then `check_engagement_permission(..., ENGAGEMENT_VIEW)` with the
admin/RO-admin/team-lead bypass. `user/{id}` is self-only. `dashboard/global` is
open at subscribe but **filtered per-recipient at broadcast time** by engagement
membership.

**What pushes today:** `create_activity_log` (the firehose → `engagement/{id}` +
`dashboard/global` + `dashboard/{engagement_id}`), note create/update/delete,
`discussion_update`, attack-graph events, per-user `notification`, and
`presence_update`/`cursor_update`. The frontend `useCollaboration` handles
presence/cursor natively; everything else arrives via `onMessage` and pages use
it as a **"something changed → refetch"** nudge (not deltas). Yjs note editing is
the one true real-time delta surface.

## 2. The scaling ceiling (most important)

- `ConnectionManager` / `yjs_store` are plain in-process objects — a broadcast
  only reaches sockets in the **same process**.
- Redis (`redis==5.0.1`) is used **only** for the JWT blacklist + SAML replay.
  No `publish`/`subscribe` touches WS.
- Prod = `uvicorn main:app` with **no `--workers`** (single worker), single
  replica (documented in `docker-compose.yml`).

**So push works today by virtue of single-process.** Any horizontal scale-out
fragments activity-log/notes/presence/Yjs across workers. **Precondition for
scaling:** add a Redis pub/sub layer to `broadcast_to_resource` (publish →
per-worker subscriber re-emits to local sockets). Yjs is harder (y-redis or
sticky sessions). Deferred while single-VPS is the deployment, but this is the
gate before leaning harder on cross-user WS.

## 3. WS push gaps (ranked) — the "gaps 1–5" work

1. **Detail `[id]` pages** (finding/testcase/asset/evidence) — presence only, no
   content invalidation. A teammate's edit leaves you on stale content until
   reload. Add the `onMessage`→invalidate pattern the list pages already use.
2. **Operations Analytics / stats page** — on-mount only (no poll *and* no WS) →
   a pinned tab is stale forever. Subscribe + invalidate `['stats']`.
3. **Infrastructure** — no `useCollaboration` at all; multi-user infra/vault
   edits invisible until reload.
4. **Admin users** — heaviest fixed poll (15s + window-focus refetch) for
   online/last-active. Add WS invalidation for user CRUD and lighten the poll.
   (Fully eliminating the poll needs heartbeat→WS broadcast — see §4.)
5. **Trim redundant fallback polls** — notifications list (60s) and dashboard
   analytics (300s) are already WS-covered.

Left alone: wordlist status (3s, job progress) and MCP health (30s) are legit
non-collaborative polls.

## 4. Effort / time-on-task metrics

**Signals that exist:**

- `activity_logs` — timestamped, per-user, per-resource, engagement-scoped. The
  right stream, **but** findings/testcases write **one row per Save** (offline
  form edit), so idle-timeout bucketing measures *time between saves*, not *time
  engaged*. A 40-min write with one Save = a single timestamp.
- Notes are the exception — Yjs autosaves ~every 3s (persisted only as 10-min-
  coalesced `updated_note` logs), so note effort is far more measurable.
- `version_history` — same Save cadence as activity_logs for findings/testcases;
  no extra resolution.
- Heartbeat (`POST /users/me/heartbeat`) — a genuine "actively interacting right
  now" signal, but a **single overwritten scalar** (`User.last_active`) with **no
  resource context**. Validates presence; can't attribute time.

**The gap:** nothing records *which resource a user is actively editing over
time*.

**Recommendation — the "activity ping" stream (one idea, two payoffs):**
Reuse the heartbeat's client gating (visible tab + real input within 2 min, ≤1
send/45s) but (a) include `resource_type` + `resource_id` (ideally focused
field/tab) and (b) **append** rows to a new table instead of overwriting a
scalar.

- **Metrics:** bucket pings per `(user, resource)` with an idle timeout → true
  time-on-task; feed the already-planned *Anonymous time-on-task aggregator*
  (`todo.md`) with min-cohort thresholds (aggregate/anonymised, lead-facing).
- **Presence bonus:** "actively editing this finding" vs merely "connected."
- **Transport:** it's a **POST** (recording, not pushing) → independent of the
  Redis/scaling question; buildable now on single-worker. The presence
  enrichment can ride the existing WS channel the client is already on.
- **Volume:** ~1 ping / 45s per active user per open resource → modest;
  append-only table + rollup/retention job.

## 5. Suggested sequencing

1. **Gaps 1–5** (this batch) — cheap, reuse existing patterns, no infra change.
2. **Activity-ping endpoint + hook** — highest leverage; unblocks effort metrics
   *and* upgrades presence; no scaling work.
3. **Time-on-task aggregator** — session bucketing + anonymised lead dashboard.
4. **Redis pub/sub WS fan-out** — only when horizontal scaling is actually on the
   table; precondition for `--workers >1` / multi-replica.

## Key references

- `backend/routers/websocket.py` — endpoints, first-frame auth, authz.
- `backend/utils/collaboration.py` — `ConnectionManager`, `broadcast_to_resource`,
  `create_activity_log`, `create_notification`.
- `backend/utils/yjs_server.py` — Yjs rooms + debounced saves.
- `frontend/src/lib/hooks/use-collaboration.ts` — generic WS client.
- `frontend/src/lib/hooks/use-activity-heartbeat.ts` — active-only gating (base
  for the resource-tied ping).
- `backend/routers/stats.py`, `backend/routers/dashboard_widgets.py` — no
  duration metric today; generic activity-log time-bucketing exists.
- `todo.md` — "Anonymous time-on-task aggregator" plan.
- `docker-compose.yml` — single-worker / single-replica deployment.
