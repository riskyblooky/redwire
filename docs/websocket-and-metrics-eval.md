# WebSocket & Effort-Metrics Evaluation

_Site-wide probe into where server-side WebSocket push helps, and how to derive
effort/time-on-task metrics ("time spent writing findings" and similar)._

Status: evaluation + plan. Findings current as of the 1.5.6 cycle.

---

## 0. TL;DR

- A capable WS layer already exists; **most list pages are already live** via the
  `activity_log` firehose. Don't rebuild it.
- **Scaling (updated 1.7.0):** the connection manager and Y.js rooms are still
  in-memory per process, but every broadcast now also goes over a **Redis
  pub/sub bus** (`utils/ws_bus.py`), so push, presence and Y.js work across
  `--workers >1` / multiple replicas. The rate limiter, intel refresh and
  wordlist Bloom filter are shared through Redis too (§2). Prod still runs
  one worker until `--workers` is set.
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

**Done in 1.7.0 — Redis fan-out (`utils/ws_bus.py`).**

- `broadcast_to_resource` delivers to local sockets, then publishes
  `{origin worker, channel, message}` on `rw:ws:bus`. Each worker's subscriber
  skips its own messages and delivers the rest to its local sockets.
- `dashboard:global` is still filtered per recipient by engagement membership.
  A remote worker runs that check itself with its own DB session.
- **Presence** (`active_users`) comes from a Redis hash per channel
  (`rw:ws:presence:<type>:<id>`, field `<worker>:<conn>`), so it covers every
  worker. Each worker refreshes `rw:ws:worker:<id>` (30s TTL). Entries from a
  worker whose key has expired, e.g. after a crash or OOM kill, are pruned
  when presence is read.
- **Y.js** is a pure relay with no server-side document, so frames and
  `peer_disconnected` notices use the same bus. The `peers` bootstrap hint
  counts room members across all workers (rooms register in the presence hash
  as `yjs:<note>`). This prevents a client that is alone on its worker from
  bootstrapping from the DB copy while a peer elsewhere holds the live
  document, which would duplicate text. The debounced save is claimed by one
  worker at a time with `SET NX`.
- If Redis is down, everything degrades to single-process delivery.
  `WS_FANOUT=false` turns the bus off.
- Verified with two uvicorn processes: presence, cursors, activity-log push,
  gated `dashboard:global`, Y.js frames and the peers hint all reach the
  other worker.

**Other per-process state — fixed in 1.7.0:**

1. **Rate limits:** slowapi stores its counters in Redis (`rate_limit.py`,
   keys `LIMITS:LIMITER/rw:rl/...`), so all workers share one budget per
   client. With Redis down it falls back to in-memory limits per worker.
   `RATE_LIMIT_STORAGE_URI` overrides the storage; tests use `memory://`.
2. **Intel feed refresh:** each cycle is claimed by one worker
   (`utils/cluster.claim("intel-refresh")`, TTL = interval − 60s).
3. **Wordlist Bloom filter:** one shared copy lives in Redis (`rw:bloom:bits`
   and `rw:bloom:meta`, about 25 MB for 14M entries). `rw:bloom:loading` is
   both the build lock and the "loading" status.
   - One worker builds it. The build now streams rows instead of paging with
     OFFSET, and other workers start in seconds without loading anything.
   - Checks read 9 bits with GETBIT. Imports SETBIT in batches, so concurrent
     imports don't lose bits. A delete rebuilds in a thread and swaps the
     bits and metadata in one MULTI.
   - If the shared copy disappears, for example after a Redis flush, the next
     check triggers a rebuild.
   - Without Redis it keeps a local in-memory filter, as before.
4. **Heartbeat and activity-ping throttles** (`routers/users.py`) are still
   per worker. That's harmless: they only allow slightly more writes.

5. **Plugin enable/disable:** a toggle is published on the bus
   (`plugin_toggle`), and every worker also resyncs from `plugin_states` every
   30s as a backstop. Without this, a disabled plugin kept serving routes on
   the other workers.
6. **Startup work:** admin bootstrap, seeding, the seed revision and the
   backfills run under a Postgres advisory lock (`utils/cluster.py`), so two
   workers can't race on unique inserts on a fresh database.

**Prod default since 1.7.0:** 2 workers (`--workers ${BACKEND_WORKERS:-2}`
in `docker-compose.yml`, set `BACKEND_WORKERS` in `.env`). Budget about
200 MB per worker on the 4 GB VPS. The dev compose stays at one worker
because `--reload` can't be combined with `--workers`.

Verified with `uvicorn --workers 2` in dev: both workers start one after the
other and join the bus, and a plugin toggle is seen by both. The control run
with `WS_FANOUT=false` showed the other worker still serving the old state.

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
4. ~~**Redis pub/sub WS fan-out**~~ — done in 1.7.0 (see §2). The remaining
   `--workers >1` blockers (rate limiter, intel refresh, Bloom filter) are
   fixed too (see §2).

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
