# RedWire plugins

Drop-in extensions for RedWire. Each plugin is a self-contained directory
under `backend/plugins/<slug>/`.

## What a plugin can do

| Capability | Where it lives | Notes |
|---|---|---|
| Backend routes | `router.py` (uses relative imports) | Mounted under `/plugins/<slug>` with `Depends(get_current_user)` |
| Event handlers | `__init__.py::setup()` — `event_bus.register(...)` | Fires on `<resource>.<action>` (CRUD) and lifecycle hooks (see below) |
| Sidebar entries | `plugin.yaml::nav_items` | Icon name resolved from `frontend/src/lib/plugin-icons.tsx` (falls back to `Plug`) |
| Dashboard widgets | `plugin.yaml::widgets` | data_source strings the widget renderer resolves |
| Admin settings | `plugin.yaml::settings` | Encrypted at rest when `type: secret` |
| DB migrations | `alembic/versions/*.py` | Own Alembic branch — see below |
| Frontend pages | `frontend/*.tsx` | Synced into the Next.js app tree at build — see below |
| RBAC | `plugin.yaml::required_permissions` | Applied to all routes; nav items can override per-entry |

## Layout

```
backend/plugins/my_plugin/
├── plugin.yaml
├── __init__.py                 # setup(app, event_bus, db_factory, manifest)
├── router.py                   # optional: FastAPI router
├── models.py                   # optional: SQLAlchemy models
├── alembic/
│   └── versions/               # optional: plugin-owned migrations
│       └── 2026-01-01_abc123_init.py
└── frontend/                   # optional: React pages
    ├── page.tsx                # → /plugins/my-plugin
    └── settings/
        └── page.tsx            # → /plugins/my-plugin/settings
```

## Migrations

Plugin migrations live on their own Alembic branch. The first migration
declares a `branch_labels`; the rest reference their predecessors:

```python
# plugins/my_plugin/alembic/versions/2026-01-01_abc123_init.py
revision = "abc123..."
down_revision = None
branch_labels = ("plugin:my-plugin",)
```

Alembic is invoked via the wrapper `backend/migrate.py` which discovers
plugin migration dirs at run time:

```bash
python migrate.py upgrade heads          # advance every branch
python migrate.py revision --autogenerate \
    --branch-label=plugin:my-plugin -m "add foo"
```

`upgrade heads` (plural) is required once multiple heads exist — the
default `alembic upgrade head` (singular) errors out with a multi-head
tree.

## Frontend pages

Anything in `plugins/<slug>/frontend/` is mirrored into
`frontend/src/app/plugins/<slug>/` by
`frontend/scripts/sync-plugin-frontends.mjs`, which runs on the Next.js
`predev` and `prebuild` hooks. Plugin authors write React the same way
they would for core, and Next's file-based router picks up the pages.

**Dev:** the dev-compose file bind-mounts `backend/plugins` into the
frontend container at `/backend-plugins:ro`, so the sync script always
sees the latest source. The pre-hooks run on every `next dev` restart.

**Prod:** the frontend Docker build context is scoped to `frontend/`, so
plugin sources aren't directly reachable at image build time. Two paths:

1. **Sync on the host before build** (simplest):
   ```bash
   node frontend/scripts/sync-plugin-frontends.mjs   # populates src/app/plugins
   docker compose -f docker-compose.prod.yml build frontend
   ```
   The synced dirs land in the build context via the existing
   `COPY . .` step. Requires Node on the deploy host.

2. **Expand the build context** to the repo root and adjust COPY paths in
   `frontend/Dockerfile`. Larger change, catches all cases.

`frontend/src/app/plugins/.gitignore` excludes synced dirs from git;
each synced dir carries a `.plugin-managed` marker so the cleanup pass
only touches what it owns (hand-authored routes at
`src/app/plugins/foo/page.tsx` are safe).

## Event hooks

CRUD events fire automatically from `create_activity_log`:
`<resource>.created`, `<resource>.updated`, `<resource>.deleted`.
Additional lifecycle hooks are emitted by core:

- `auth.login.success` / `auth.login.failed`
- `user.created`
- `finding.status_changed` (payload includes old_status + new_status)
- `report.generated`

Wildcards work: `event_bus.register("finding.*", handler)` sees every
finding event.
