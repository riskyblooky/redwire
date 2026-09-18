# RedWire — Developer Onboarding & Architecture Map

> Orientation guide for any human or agent picking up development on RedWire.
> Read this first, then `CLAUDE.md` for the hard conventions, then the relevant
> skill in `.claude/skills/` for the area you're working in.
>
> **Last mapped:** 2026-06-03 (against `main`). Treat counts as approximate —
> verify against the tree before relying on them.

---

## 1. What RedWire is

A **self-hosted red-team operations management platform** built and maintained by
a single developer for internal/production use. It manages the full lifecycle of
offensive-security engagements:

engagements → assets/infra → findings (CVSS-scored) → evidence → credential vault
→ cleanup artifacts → runbooks → test cases → reporting (PDF/DOCX) → team
collaboration, with an MCP server and a plugin system layered on top.

Companion docs at repo root:
- `README.md` — public-facing overview & quick start
- `GETTING_STARTED.md` — first-run setup
- `FEATURES.md` / `feature_analysis.md` — feature inventory & deeper analysis
- `MIGRATION.md` — data/version migration notes
- `SECURITY.md` — security policy, GHSA acknowledgements
- `todo.md` — **the live backlog / current focus** (check this for what's in flight)
- `CLAUDE.md` — binding conventions (the source of truth for *how* to write code here)

---

## 2. Tech stack (one-liner)

| Layer | Stack |
|-------|-------|
| Backend | Python **FastAPI** (async), **SQLAlchemy 2.x**, PostgreSQL 15, Redis, MinIO (S3), Alembic. Async driver `asyncpg`; migrations use sync `psycopg2`. |
| Frontend | **Next.js 14** (App Router), React 18, TypeScript, **Tailwind v4** (no config file — `@theme {}` in `globals.css`), shadcn/ui (slate, **dark only**), **TanStack Query**, Zustand, sonner, TipTap. |
| Infra | Docker Compose (dev + prod), Nginx reverse proxy, Certbot. |
| Extras | `mcp-server/` (Starlette + SSE) exposes RedWire as MCP tools; plugin system loads from `backend/plugins/`. |

Rough scale: ~45k LOC of backend Python, ~220 TS/TSX files, **47 routers**,
**49 models**, **~50 frontend query-hook files**, **93 Alembic migrations**.

---

## 3. Repo layout (the parts that matter)

```
backend/
  main.py            App entry — lifespan, CORS, middleware, router registration, OpenAPI tags
  database.py        Async engine, Base, AuditMixin, get_db dependency
  rate_limit.py      slowapi limiter
  plugin_loader.py   Plugin discovery/load/mount
  auth/              jwt, password, totp, crypto, ldap_auth, saml_auth, rbac, permissions, dependencies
  models/            SQLAlchemy models — UUID PKs, AuditMixin
  schemas/           Pydantic request/response (~31 files)
  routers/           FastAPI routers — prefix declared ON the router
  utils/             storage, vault_crypto, collaboration (activity logs), report_generator,
                     automation_engine, event_bus, email_service, ssrf, hash_utils, versioning,
                     yjs_server (collab), parsers/
  plugins/           servicenow_cmdb, shodan_enricher (each: plugin.yaml + __init__.py + router.py)
  alembic/versions/  Migrations — filename: YYYY-MM-DD_<revid>_<desc>.py
  seed_*.py          Seed scripts (defaults, rbac, permissions, templates, skills, demo, test data)
frontend/src/
  app/               App Router pages (engagements, findings, assets, reports, templates, admin, …)
  components/        UI (shadcn under components/ui)
  lib/
    api.ts           THE axios instance (JWT inject + refresh-race protection) — never make ad-hoc instances
    types.ts         Shared TS types
    cvss31.ts        CVSS 3.1 scoring
    hooks/           One use-<resource>.ts per resource (hook + exported TS interfaces)
  stores/            Zustand: auth-store, engagement-store, user-settings-store
  middleware.ts      Route gating via has_session cookie
mcp-server/          server.py (forwards session JWT to backend)
nginx/               Nginx config + Certbot volumes
scripts/             deploy_server.sh, seed_*.sql, init-ssl.sh, generate_encryption_keys.py, sync_templates.sh
auth-test/           OpenLDAP + Keycloak fixtures for SSO/LDAP testing
```

---

## 4. How the backend boots (`main.py` lifespan)

The `lifespan` context manager (not the legacy `@app.on_event` hooks) does the real work, **in order**:

1. **Validate at-rest encryption keys, fail closed** — `vault_crypto.validate_key()` and
   `totp_crypto.validate_key()`. The app **refuses to start** unless `VAULT_ENCRYPTION_KEY`
   and `TOTP_ENCRYPTION_KEY` are set and are valid Fernet keys (GHSA-pg99-33rm-7wgq).
   Never silently derive them from `JWT_SECRET`.
2. **Discover + load + mount plugins** from `plugins/` (`plugin_registry`).
3. **Seed**: admin user (from env) → default groups/roles → `seed_all_defaults()`
   (tags, types, skills, templates…). Seed failures log a WARN and do **not** block startup.
4. **Background tasks**: Bloom filter load (`hash_utils.bloom_service`, millions of rows — async,
   non-blocking) and intel-feed refresh. Both cancelled cleanly on shutdown.

Other app wiring:
- **CORS**: origins from `CORS_ORIGINS` env (comma-separated); defaults to localhost if unset.
  `allow_credentials=True` (needed for the HttpOnly refresh cookie).
- **`update_last_active` middleware**: throttled (once/60s per user) write of `User.last_active`,
  skipping `/health`, `/docs`, `/uploads/`, `/ws`, etc.
- **`/uploads` static mount**, `/health`, `/docs`, `/redoc`.
- **Rate limiting** via slowapi (`app.state.limiter`).

---

## 5. Auth model (read before touching auth)

- **Access token**: short-lived JWT, stored in `localStorage`, sent as `Authorization: Bearer`.
- **Refresh token**: **HttpOnly cookie** set by `/auth/login`; JS calls `/auth/refresh` with
  `withCredentials: true` and reads the new access token from the JSON body (GHSA-gv65-p25x-qrqj).
  > ⚠️ `CLAUDE.md` says "JWT tokens are in localStorage" — that's true for the **access** token
  > only. The **refresh** token moved to an HttpOnly cookie. Don't "fix" the access-token-in-
  > localStorage unless explicitly hardening token storage; do respect the cookie flow.
- **Frontend refresh** (`lib/api.ts`): reactive 401 retry with race protection + a proactive
  refresh every 28 min. Auth endpoints (`/auth/login|register|verify-2fa`) are excluded from the
  retry loop.
- **API tokens**: long-lived tokens (`ro`/`rw` scopes) resolved in `auth/dependencies.py`
  (`_resolve_api_token`) — an alternative to JWT for scripting/automation.
- **SSO/Directory**: SAML (`saml_auth.py`) + LDAP (`ldap_auth.py`); TOTP 2FA (`totp.py`,
  secrets encrypted via `auth/crypto.py`).

### RBAC / permission checks (`auth/rbac.py`, `auth/dependencies.py`)
- Every endpoint: `current_user: User = Depends(get_current_user)` unless explicitly public.
- Engagement-scoped writes: `await check_engagement_permission(user_id, engagement_id, "<perm>", db)`.
- Helpers: `check_engagement_role`, `resolve_engagement_scope` / `scope_to_assignments`
  (for filtering list queries to a user's assigned engagements), `can_modify_resource`,
  `require_roles`, `require_write`.

---

## 6. Backend conventions (the short version — full rules in `CLAUDE.md`)

- Routers declare their **own** prefix: `APIRouter(prefix="/foo", tags=["foo"])`; `main.py`
  calls `app.include_router(foo.router)` with **no app-level prefix**.
- Models: `str(uuid.uuid4())` PKs, inherit `AuditMixin` (never redeclare `created_at`/`updated_at`).
- Significant create/update/delete → `create_activity_log` (`utils/collaboration.py`) for audit trail;
  versioned resources also snapshot via `utils/versioning.py`.
- **Never f-string raw SQL** — ORM or `sa.text(...)` with bound params only.
- Enum values are **UPPERCASE** to match the Postgres enum convention (`CRITICAL`, `OPEN`).
- Adding a new resource end-to-end? Follow the **`new-feature`** skill checklist.

### Migrations (see **`alembic`** skill)
- `docker compose run --rm backend alembic revision --autogenerate -m "..."`, then **rename** the
  file to `YYYY-MM-DD_<revid>_<desc>.py`, review, apply.
- New column on a populated table → `nullable=True` or `server_default`.
- Renaming an enum value → `ALTER TYPE ... RENAME VALUE` guarded by an existence check
  (pattern: `2026-04-28_..._fix_enum_casing_and_missing_cols.py`).

---

## 7. Frontend conventions (short version — full rules in `frontend-conventions` skill)

- Default-import `api` from `lib/api` (axios). **Never** build ad-hoc axios instances — they bypass auth.
- One TanStack Query hook file per resource: `lib/hooks/use-<resource>.ts`; export the resource's
  TS interfaces from the same file.
- List queries: `staleTime: 30_000`. QueryClient default (`providers.tsx`): `staleTime: 60_000`,
  `refetchOnWindowFocus: false`.
- Mutations invalidate by **broad** query key (`['findings']`) — TanStack matches partials.
- Toasts: `sonner` (dark theme already wired).
- **Dark only.** Never add a light variant. Use semantic Tailwind (`bg-card`, `text-muted-foreground`,
  `hover:bg-accent`) — no raw hex/grays. Severity: Critical=red-500, High=orange-500, Medium=yellow-500,
  Low=blue-400, Info=slate-400.
- Route gating is via `has_session` cookie in `middleware.ts` + the `use-navigation-guard` hook.

---

## 8. Feature areas → where the code lives

Each row is roughly: **router** (`backend/routers/`) ↔ **model(s)** (`backend/models/`) ↔
**hook** (`frontend/src/lib/hooks/use-*.ts`) ↔ **page** (`frontend/src/app/`).

| Area | Backend router(s) | Notes |
|------|-------------------|-------|
| Auth / users / admin | `auth`, `users`, `admin`, `permissions`, `auth_settings`, `api_tokens` | JWT, TOTP, LDAP/SAML, RBAC, registration codes |
| Engagements | `engagements`, `engagements_transfer` | core scope; transfer = reassign ownership |
| Findings | `findings`, `tags`, `discussions` | CVSS-scored; evidence + threaded discussion |
| Assets / infra | `assets`, `infra` | hosts, ports, infra items + per-infra vault |
| Vault | `vault` | Fernet-encrypted secrets, engagement-scoped |
| Evidence | `evidence`, `markdown_images` | MinIO-backed uploads |
| Cleanup | `cleanup_artifacts` | post-engagement teardown tracking |
| Test cases / runbooks | `testcases`, `testcase_templates`, `runbooks`, `skills` | repeatable procedures |
| Reporting | `reports`, `report_layouts`, `report_layout_templates`, `report_themes` | PDF/DOCX, `utils/report_generator.py` |
| Templates | `templates` (findings), `testcase_templates`, `configurable_types`, `clients` | reusable definitions & custom types |
| Intel | `intel`, `attack_graph`, `attack_techniques` | feeds, ATT&CK mapping, graph layout |
| Offensive tooling | `spray`, `wordlist`, `imports` | password spray tracking, wordlists, scan imports (`utils/parsers/`) |
| Collaboration | `notes`, `notifications`, `calendar`, `discussions`, `websocket` | real-time via `utils/yjs_server.py` |
| Automation | `automations` | `utils/automation_engine.py` + `event_bus` |
| AI | `ai` | in-app chatbot, `models/ai_settings.py` |
| Dashboards / analytics | `dashboard_widgets`, `analytics`, `stats`, `search` | |
| Plugins | `plugins` | drives `plugin_loader.py` registry |

---

## 9. Plugins & MCP

- **Plugins** (`backend/plugins/`): each = `plugin.yaml` manifest + `__init__.py` + optional
  `router.py`. Discovered/loaded/mounted at startup; can subscribe to the `event_bus` and define
  settings. Examples: `servicenow_cmdb`, `shodan_enricher`. See the **`plugins`** skill.
- **MCP server** (`mcp-server/server.py`): Starlette + SSE; forwards the session JWT to the backend
  so LLM clients (e.g. Claude Desktop) and the in-app chatbot can call RedWire as tools.
  See the **`mcp-server`** skill.

---

## 10. Running it locally (see **`dev-workflow`** skill for full detail)

```bash
docker compose up -d          # full dev stack
```

Dev ports (all bound to `127.0.0.1` except Nginx):

| Service | Port |
|---------|------|
| Frontend (Next.js) | 3000 |
| Backend (FastAPI) | 8000 (`/docs` for Swagger) |
| Postgres | 5432 |
| Redis | 6379 |
| MinIO | 9000 (API) / 9001 (console) |
| MCP server | 3001 |
| Nginx | 8080 (http) / 8443 (https) |

**SSO/LDAP testing overlay** (adds OpenLDAP + Keycloak):
```bash
docker compose -f docker-compose.yml -f docker-compose.auth-test.yml up -d
```
Fixtures live in `auth-test/`.

> Env: copy `.env.example` → `.env`. `VAULT_ENCRYPTION_KEY` + `TOTP_ENCRYPTION_KEY` **must** be set
> (app fails closed without them). Generate with `scripts/generate_encryption_keys.py`.

---

## 11. Production & deploy (see **`prod-build`** skill)

- `docker-compose.prod.yml` + Nginx + Certbot (Let's Encrypt). Deploy via `scripts/deploy_server.sh`.
- **Deploy target is a 4GB VPS.** Frontend prod build heap capped at 2GB
  (`NODE_OPTIONS=--max-old-space-size=2048` in the Dockerfile) — don't raise it.
- Internal services (postgres/redis/minio/mcp) have **no public port bindings** in prod. Don't add them.
- The deploy script **wipes** `frontend/src`, `frontend/public`, `backend/app`, `backend/alembic`
  before extracting `redwire_migration_package.zip`. Don't keep anything in those dirs that isn't in
  the zip. (Package build steps are in the **`git-workflow`** skill.)
- **`VAULT_ENCRYPTION_KEY` must be backed up separately from the DB.** Losing it = losing all vault data.
  Key rotation: `backend/rotate_encryption_keys.py` (accepts `OLD_*_ENCRYPTION_KEY`).

---

## 12. Security workflow (this is a security product — it has its own GHSA process)

- `SECURITY.md` holds the policy + acknowledgements; `.claude/security-advisories/` holds triage queues.
- Inbound vuln reports follow the **`vulnerability-response`** skill (triage → fix in a private
  advisory fork → publish GHSA → request CVE → land fix → update acknowledgements). The
  **`vulnerability-fix-loop`** skill is the per-advisory execution loop.
- **Advisory fix landing**: patches land in the GitHub-generated **temporary private fork**, never
  directly in `redwire-public`; the maintainer owns all remote ops on the public repo. (The temp fork
  has API quirks: `gh pr create` 500s and `gh pr comment` is forbidden — create/comment via web UI,
  then `gh pr edit` to overlay title/body.)
- Auditing/fixing: **`find-and-fix-vulnerabilities`** (grep recipes) + **`security-patterns`**
  (correct-by-construction patterns). Notable hardening already in place: SSRF guard (`utils/ssrf.py`),
  fail-closed key validation, HttpOnly refresh cookie, rate limiting.

---

## 13. Skills index (`.claude/skills/`)

Auto-loaded by topic; also invocable explicitly. Start here for any task:

| Skill | Use when |
|-------|----------|
| `dev-workflow` | starting/rebuilding the stack, ports, env, resetting the DB |
| `new-feature` | adding a resource end-to-end (model→schema→router→migration→hooks) |
| `alembic` | migrations, enum/column safety, merging heads |
| `frontend-conventions` | hooks, stores, forms, tables, axios refresh, toasts |
| `theme` | colors, shadcn, Tailwind v4, dark-mode tokens, severity colors |
| `security-patterns` | auth, RBAC, vault crypto, validation, file upload, audit logging |
| `find-and-fix-vulnerabilities` | security audits + fix patterns |
| `vulnerability-response` / `vulnerability-fix-loop` | the GHSA/CVE lifecycle |
| `mcp-server` | MCP server + chatbot auth |
| `plugins` | plugin manifest, lifecycle, event bus, settings |
| `git-workflow` | commits, branching, deploy zip |
| `prod-build` | prod compose, deploy script, SSL, backup/restore |
| `troubleshooting` | runtime errors, build/startup failures, MinIO/vault/Nginx symptoms |
| `testing` | test suite state (note: **no real suite yet**) |

---

## 14. Gotchas & things that look like bugs but aren't

- **Access token in `localStorage`** is intentional (refresh token is the HttpOnly cookie). Don't flag.
- **Frontend `node_modules` and `.next` are named Docker volumes**, not bind mounts — for WSL FS perf.
  Don't switch to bind mounts.
- **Tailwind v4 has no config file** — theme tokens live in `@theme {}` in `globals.css`.
- **Seed failures don't block startup** (logged WARN) — a missing seed is not necessarily an error.
- **`.claude/` is gitignored** — skills and this repo's agent config are *not* shared via git
  (this file, `ONBOARDING.md`, lives at root precisely so it is).
- **No real test suite exists yet** (despite stray `test_*.py` / `pytest_out*.txt` in `backend/`).
  Don't assume `pytest` green = covered.
- **There are loose diagnostic scripts in `backend/`** (`check_models.py`, `check_tables.py`,
  `db_diag.py`, `inspect_schema.py`, `manual_migrate.py`) — ad-hoc tooling, not part of the app.
```
