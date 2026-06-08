"""
Plugin Loader — Discovers, validates, and mounts plugins from the plugins/ directory.

Each plugin is a directory containing:
  - plugin.yaml   (manifest with metadata, hooks, settings)
  - __init__.py    (entry point with setup(app, event_bus, db_factory) function)
  - router.py      (optional FastAPI router)

Lifecycle:
  1. discover_plugins() scans plugins/ for valid manifests
  2. load_plugin() imports the module and calls setup()
  3. mount_plugins() attaches routers to the FastAPI app
"""

import importlib
import importlib.util
import os
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from fastapi import Depends, FastAPI, HTTPException, status


@dataclass
class PluginManifest:
    """Parsed plugin.yaml."""
    id: str                     # directory name = plugin slug
    name: str
    version: str = "1.0.0"
    author: str = ""
    description: str = ""
    min_redwire_version: str = "1.0.0"
    provides: dict = field(default_factory=dict)
    settings: list[dict] = field(default_factory=list)
    widgets: list[dict] = field(default_factory=list)
    nav_items: list[dict] = field(default_factory=list)
    required_permissions: list[str] = field(default_factory=list)
    enabled: bool = True


@dataclass
class LoadedPlugin:
    """A plugin that has been discovered and loaded."""
    manifest: PluginManifest
    module: Any = None          # The imported Python module
    router: Any = None          # FastAPI router (if provides.routes)
    error: str | None = None    # Load error message

    @property
    def id(self) -> str:
        return self.manifest.id

    @property
    def slug(self) -> str:
        return self.manifest.id.replace("_", "-")

    @property
    def has_routes(self) -> bool:
        return self.manifest.provides.get("routes", False) and self.router is not None

    @property
    def has_event_listeners(self) -> bool:
        return self.manifest.provides.get("event_listeners", False)

    @property
    def has_widgets(self) -> bool:
        return bool(self.manifest.widgets)

    @property
    def has_nav_items(self) -> bool:
        return bool(self.manifest.nav_items)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "slug": self.slug,
            "name": self.manifest.name,
            "version": self.manifest.version,
            "author": self.manifest.author,
            "description": self.manifest.description,
            "enabled": self.manifest.enabled,
            "has_routes": self.has_routes,
            "has_event_listeners": self.has_event_listeners,
            "has_widgets": self.has_widgets,
            "has_nav_items": self.has_nav_items,
            "widgets": self.manifest.widgets,
            "nav_items": self.manifest.nav_items,
            "settings_schema": self.manifest.settings,
            "error": self.error,
        }


def _make_enabled_check(plugin: "LoadedPlugin"):
    """Build a per-plugin dependency that 503s when the plugin is disabled.

    Closes over the live ``LoadedPlugin`` object so a subsequent
    ``manifest.enabled = False`` flip (from the toggle handler) takes
    effect immediately, without needing to unmount any routes
    (GHSA-4jrh-3m3r-p448).
    """
    def _check_enabled():
        if not plugin.manifest.enabled:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Plugin '{plugin.id}' is disabled",
            )
    return _check_enabled


class PluginRegistry:
    """Central registry of all discovered plugins."""

    def __init__(self):
        self.plugins: dict[str, LoadedPlugin] = {}
        self._plugins_dir: str = ""

    def discover(self, plugins_dir: str = "plugins") -> list[LoadedPlugin]:
        """Scan plugins/ directory for valid plugin manifests."""
        self._plugins_dir = plugins_dir
        os.makedirs(plugins_dir, exist_ok=True)

        discovered = []
        plugins_path = Path(plugins_dir)

        for entry in sorted(plugins_path.iterdir()):
            if not entry.is_dir() or entry.name.startswith((".", "_")):
                continue

            manifest_path = entry / "plugin.yaml"
            if not manifest_path.exists():
                # Also check plugin.yml
                manifest_path = entry / "plugin.yml"
                if not manifest_path.exists():
                    continue

            try:
                manifest = self._parse_manifest(entry.name, manifest_path)
                plugin = LoadedPlugin(manifest=manifest)
                discovered.append(plugin)
                self.plugins[plugin.id] = plugin
                print(f"  📦 Discovered plugin: {manifest.name} v{manifest.version}")
            except Exception as e:
                print(f"  ❌ Error parsing {entry.name}/plugin.yaml: {e}")
                traceback.print_exc()

        return discovered

    def load_all(self, app: FastAPI, event_bus, db_factory):
        """Import and initialize all discovered plugins."""
        for plugin_id, plugin in self.plugins.items():
            if not plugin.manifest.enabled:
                print(f"  ⏸️  Plugin '{plugin.manifest.name}' is disabled, skipping")
                continue
            try:
                self._load_plugin(plugin, app, event_bus, db_factory)
                print(f"  ✅ Loaded plugin: {plugin.manifest.name}")
            except Exception as e:
                plugin.error = str(e)
                print(f"  ❌ Error loading plugin '{plugin.manifest.name}': {e}")
                traceback.print_exc()

    def mount_routes(self, app: FastAPI):
        """Mount all plugin routers onto the FastAPI app.

        GHSA-2rv7-jv5j-m4jg: every plugin endpoint inherits
        ``Depends(get_current_user)`` at the include site so a plugin
        author who forgets per-route auth doesn't accidentally expose a
        pre-auth surface. Imported lazily to avoid a circular import
        with ``auth.dependencies``.

        GHSA-4jrh-3m3r-p448: attach a per-plugin runtime gate so a
        toggle-off via ``PUT /plugins/{id}/toggle`` actually disables
        the HTTP surface. Routes stay mounted (no router surgery, no
        race with in-flight requests) but the dependency refuses to
        dispatch when ``plugin.manifest.enabled`` is False.
        """
        from auth.dependencies import get_current_user

        for plugin in self.plugins.values():
            if plugin.has_routes and plugin.manifest.enabled and not plugin.error:
                prefix = f"/plugins/{plugin.slug}"
                app.include_router(
                    plugin.router,
                    prefix=prefix,
                    tags=[f"plugin:{plugin.slug}"],
                    dependencies=[
                        Depends(get_current_user),
                        Depends(_make_enabled_check(plugin)),
                    ],
                )
                print(f"  🔌 Mounted routes: {prefix}")

    def get_all_widgets(self) -> list[dict]:
        """Collect widget definitions from all active plugins."""
        widgets = []
        for plugin in self.plugins.values():
            if plugin.manifest.enabled and not plugin.error and plugin.has_widgets:
                for w in plugin.manifest.widgets:
                    widgets.append({
                        **w,
                        "id": f"plugin:{plugin.id}:{w.get('id', 'default')}",
                        "plugin_id": plugin.id,
                        "plugin_name": plugin.manifest.name,
                    })
        return widgets

    def get_all_nav_items(self) -> list[dict]:
        """Collect nav items from all active plugins."""
        items = []
        for plugin in self.plugins.values():
            if plugin.manifest.enabled and not plugin.error and plugin.has_nav_items:
                for nav in plugin.manifest.nav_items:
                    items.append({
                        **nav,
                        "plugin_id": plugin.id,
                        "plugin_name": plugin.manifest.name,
                        "path": nav.get("path", f"/plugins/{plugin.slug}"),
                    })
        return items

    def _parse_manifest(self, dir_name: str, path: Path) -> PluginManifest:
        """Parse plugin.yaml into a PluginManifest."""
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        return PluginManifest(
            id=dir_name,
            name=data.get("name", dir_name),
            version=str(data.get("version", "1.0.0")),
            author=data.get("author", ""),
            description=data.get("description", ""),
            min_redwire_version=str(data.get("min_redwire_version", "1.0.0")),
            provides=data.get("provides", {}),
            settings=data.get("settings", []),
            widgets=data.get("widgets", []),
            nav_items=data.get("nav_items", []),
            required_permissions=data.get("required_permissions", []),
            enabled=data.get("enabled", True),
        )

    def _load_plugin(self, plugin: LoadedPlugin, app: FastAPI, event_bus, db_factory):
        """Import plugin module and call its setup function."""
        plugin_dir = Path(self._plugins_dir) / plugin.id

        # Add plugin directory to sys.path so a plugin's own internal
        # modules can import each other by short name. Append rather than
        # prepend so backend / stdlib modules always win name collisions —
        # a plugin shipping `auth.py` / `permissions.py` / `jwt.py` no
        # longer shadows the real module (GHSA-2rv7-jv5j-m4jg).
        plugin_dir_str = str(plugin_dir.resolve())
        if plugin_dir_str not in sys.path:
            sys.path.append(plugin_dir_str)

        # Import __init__.py
        init_path = plugin_dir / "__init__.py"
        if init_path.exists():
            spec = importlib.util.spec_from_file_location(
                f"plugins.{plugin.id}", str(init_path)
            )
            module = importlib.util.module_from_spec(spec)
            sys.modules[f"plugins.{plugin.id}"] = module
            spec.loader.exec_module(module)
            plugin.module = module

            # Call setup() if it exists
            if hasattr(module, "setup"):
                module.setup(
                    app=app,
                    event_bus=event_bus,
                    db_factory=db_factory,
                    manifest=plugin.manifest,
                )

        # Import router.py if plugin provides routes
        if plugin.manifest.provides.get("routes", False):
            router_path = plugin_dir / "router.py"
            if router_path.exists():
                spec = importlib.util.spec_from_file_location(
                    f"plugins.{plugin.id}.router", str(router_path)
                )
                router_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(router_module)
                if hasattr(router_module, "router"):
                    plugin.router = router_module.router


# Singleton
plugin_registry = PluginRegistry()
