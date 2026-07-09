# RedWire plugins

Drop-in extensions for RedWire. Each plugin is a self-contained
directory under `backend/plugins/<slug>/`.

## What a plugin can do

| Capability | Where it lives | Notes |
|---|---|---|
| Backend routes | `router.py` (uses relative imports) | Mounted under `/plugins/<slug>` with `Depends(get_current_user)` + a runtime enable-check |
| Event handlers | `__init__.py::setup()` — `event_bus.register(...)` | Fires on `<resource>.<action>` (CRUD) and lifecycle hooks |
| Sidebar entries | `plugin.yaml::nav_items` | Icon name resolved from `frontend/src/lib/plugin-icons.tsx` (falls back to `Plug`) |
| Extension slots | `plugin.yaml::extensions` + `frontend/extensions/*.tsx` | Core pages render `<PluginSlot slot="..." />`; plugins register components against named slots |
| Dashboard widgets | `plugin.yaml::widgets` | data_source strings the widget renderer resolves |
| Admin settings | `plugin.yaml::settings` | Encrypted at rest when `type: secret` |
| DB migrations | `alembic/versions/*.py` | Own Alembic branch — see below |
| Frontend pages | `frontend/*.tsx` | Synced into the Next.js app tree at build — see below |
| RBAC | `plugin.yaml::required_permissions` | Applied to all routes; nav items and extensions can override per-entry |

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
└── frontend/                   # optional: React pages + extensions
    ├── page.tsx                # → /plugins/my-plugin
    ├── settings/
    │   └── page.tsx            # → /plugins/my-plugin/settings
    └── extensions/             # → registered against extension slots
        └── my-tab.tsx          # rendered by <PluginSlot slot="..." />
```

## Frontend pages — how they get built

Anything in `plugins/<slug>/frontend/` is mirrored into
`frontend/src/app/plugins/<slug>/` by
`frontend/scripts/sync-plugin-frontends.mjs`, which runs on the
Next.js `predev` and `prebuild` hooks. Plugin authors write React the
same way they would for core, and Next's file-based router picks up
the pages — no runtime module loader, no dynamic requires. Pages get
tree-shaken and code-split like any other route.

**Dev:** the dev-compose file bind-mounts `backend/plugins` into the
frontend container at `/backend-plugins:ro`, so the sync script
always sees the latest source. The pre-hooks run on every `next dev`
restart. If you add a plugin page, restart the frontend container.

**Prod:** the frontend Docker build context is the repo root (see
`docker-compose.yml`), and `frontend/Dockerfile` `COPY
backend/plugins/ /backend-plugins/` in its builder stage. So `next
build` runs `sync-plugin-frontends.mjs` with plugin sources in scope,
and plugin pages are baked into the resulting image. **A plugin
change requires rebuilding the frontend image:**

```bash
docker compose build frontend
docker compose up -d frontend
```

`.dockerignore` at the repo root keeps the build context lean —
without it the daemon would ship `.git`, `node_modules`, `.next`,
`evidence/`, backups, etc. before COPY ran.

`frontend/src/app/plugins/.gitignore` excludes synced dirs from git;
each synced dir carries a `.plugin-managed` marker so the cleanup
pass only touches what it owns (hand-authored routes at
`src/app/plugins/foo/page.tsx` are safe).

### Extension slots (how plugins inject into core pages)

Core pages call `<PluginSlot slot="engagement.tabs" props={...} />`
anywhere they want plugin-registered content. A plugin registers
against a slot in two places:

1. **Manifest** — declare each contribution in `plugin.yaml`:

    ```yaml
    extensions:
      engagement.tabs:
        - component: cmdb-tab           # basename of the .tsx file
          label: "ServiceNow CMDB"
          required_permissions:
            - "engagement_view"
    ```

2. **Component file** at `frontend/extensions/<component>.tsx`,
   default-exporting a React component. The component receives the
   props the core render site forwards, plus an `entry` prop with the
   manifest entry.

At sync time, `sync-plugin-frontends.mjs` writes
`frontend/src/app/plugins/_extensions.generated.tsx` mapping
`"<slug>:<component>"` → the component's default export. `<PluginSlot>`
fetches its list from `GET /plugins/extensions/{slot}` (backend gates
by the caller's global permissions AND the plugin's `enabled` state)
and looks each entry up in that generated registry. If the manifest
advertises a component but no file matches, the console warns and
that entry is skipped — nothing crashes.

Current slots in use:
- `engagement.tabs` — additional tabs on the engagement detail page.

New slots are just strings — add a `<PluginSlot slot="foo.bar" />`
somewhere in core and plugins can start targeting it.

## Migrations

Plugin migrations live on their own Alembic branch so they don't
interleave with core migration IDs and can be released independently.
The first migration declares a `branch_labels`; the rest reference
their predecessors on that branch:

```python
# plugins/my_plugin/alembic/versions/2026-01-01_abc123_init.py
revision = "abc123..."
down_revision = None
branch_labels = ("plugin:my-plugin",)

def upgrade() -> None:
    op.create_table(
        "my_plugin_thing",
        sa.Column("id", sa.String(36), primary_key=True),
        ...
    )
```

Follow-up migrations on the same plugin set `down_revision` to the
previous plugin migration's revision — do NOT set `branch_labels`
again (Alembic errors if a label is re-declared).

Alembic is invoked via the wrapper `backend/migrate.py`, which
discovers plugin migration dirs at run time:

```bash
python migrate.py upgrade heads          # advance every branch
python migrate.py revision --autogenerate \
    --branch-label=plugin:my-plugin -m "add foo"
python migrate.py downgrade plugin:my-plugin@-1   # step one back on the plugin branch
```

`upgrade heads` (plural) is required once multiple heads exist — the
default `alembic upgrade head` (singular) errors out with a
multi-head tree.

**Filename convention** matches core: `YYYY-MM-DD_<revid>_<desc>.py`.

**Column safety** matches core (see `.claude/skills/alembic/`): new
columns on populated tables need `nullable=True` or `server_default`.
Renaming enum values requires the guarded `ALTER TYPE ... RENAME
VALUE` pattern.

## Enable / disable — what actually gates the plugin

Toggling a plugin off (via admin UI or `PUT /plugins/<id>/toggle`)
flips `manifest.enabled` in-memory. Once flipped:

- Routes stay mounted for HTTP identity but a runtime dependency
  refuses to dispatch, so requests return 503 without invoking plugin
  code (GHSA-4jrh-3m3r-p448).
- `get_all_nav_items`, `get_all_widgets`, and `get_extensions` all
  filter on `enabled` — the sidebar link, the widget catalog, and
  every `<PluginSlot>` stop returning the plugin's entries.
- Event handlers registered on the bus still fire — disabling doesn't
  unhook them (loader-time registration). If your handler must
  respect the toggle, check `manifest.enabled` at the top of the
  handler.
- Migrations already applied are NOT rolled back.

The frontend admin page invalidates `['plugins']`,
`['plugin-nav-items']`, and `['plugin-extensions']` on toggle so
every consumer refetches immediately — if you add a new query that
depends on plugin state, invalidate the same keys or your surface
will lag until its staleTime elapses.

## Event hooks

CRUD events fire automatically from `create_activity_log`:
`<resource>.created`, `<resource>.updated`, `<resource>.deleted`.
Additional lifecycle hooks are emitted by core:

- `auth.login.success` / `auth.login.failed`
- `user.created`
- `finding.status_changed` (payload includes old_status + new_status)
- `report.generated`

Wildcards work: `event_bus.register("finding.*", handler)` sees every
finding event. Always pass `plugin_id=manifest.id` when registering —
it's used for diagnostics and future teardown.
