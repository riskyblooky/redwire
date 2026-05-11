# Backend plugins

Drop-in plugins for the RedWire backend. The platform discovers anything in this directory on startup.

## Plugin layout

backend/plugins//
├── plugin.yaml          # Manifest (name, version, description, settings schema)
├── init.py          # Plugin entry point (lifecycle hooks, event handlers)
└── router.py            # Optional: FastAPI router mounted under /plugins/

See `backend/plugins/__init__.py` and the plugin loader in `backend/utils/` for the discovery and registration logic.
