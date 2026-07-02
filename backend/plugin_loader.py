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
    # ``extensions`` maps a slot name (e.g. ``engagement.tabs``) to a list of
    # entries the plugin wants to render into that slot. Each entry is a
    # dict with:
    #   * ``component``: the file basename under ``frontend/extensions/``
    #                    (without the .tsx). Loaded via the generated
    #                    registry in ``frontend/src/app/plugins/
    #                    _extensions.generated.tsx``.
    #   * ``label``: display name (used for tabs / section headings).
    #   * ``required_permissions`` (optional): per-entry RBAC gate.
    # See PluginRegistry.get_extensions for the read path.
    extensions: dict = field(default_factory=dict)
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


def _resolve_permission(name: str):
    """Look up a Permission by either its value or its member name.

    Plugin authors write permissions in yaml, and different sources use
    different conventions — the auth/permissions module refers to
    ``Permission.ASSET_VIEW`` (member name, uppercase), while the
    stored enum value is ``"asset_view"`` (lowercase snake_case).
    Accept either so a manifest doesn't fail on casing.
    """
    from models.permission import Permission
    if not isinstance(name, str):
        raise ValueError(f"not a string: {name!r}")
    key = name.strip()
    # Value form (lowercase) — the canonical DB representation.
    try:
        return Permission(key.lower())
    except ValueError:
        pass
    # Member-name form (uppercase) — how it reads in Python code.
    try:
        return Permission[key.upper()]
    except KeyError:
        raise ValueError(f"unknown permission: {name!r}")


def _make_permission_check(plugin: "LoadedPlugin"):
    """Build a per-plugin route dependency that enforces the manifest's
    ``required_permissions`` list.

    Each entry is a global :class:`Permission` — either the enum value
    (``"finding_view"``) or the member name (``"FINDING_VIEW"``). A
    caller must hold ALL listed permissions to reach any route mounted
    by the plugin. Empty/missing list = no additional gate beyond the
    mount-level ``get_current_user``.

    An unknown permission name in the manifest aborts every request to
    the plugin with 403 — a plugin author's typo shouldn't silently
    become "no restriction".
    """
    from auth.dependencies import get_current_user
    from database import get_db

    required = list(plugin.manifest.required_permissions or [])

    async def _check(
        current_user=Depends(get_current_user),
        db=Depends(get_db),
    ):
        if not required:
            return
        from auth.permissions import has_global_permission
        try:
            required_enum = [_resolve_permission(p) for p in required]
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Plugin '{plugin.id}' declares an unknown "
                    f"required_permission: {e}"
                ),
            )
        for perm in required_enum:
            if not await has_global_permission(current_user, perm, db):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Missing required permission: {perm.value}",
                )

    return _check


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
        """Import and initialize all discovered plugins.

        Two gates run before ``_load_plugin`` actually exec's the
        plugin module:
          - ``min_redwire_version`` — refuses to load a plugin
            authored against a future API. GHSA-2rv7 follow-up.
          - Signature verification under PLUGIN_VERIFY=preferred /
            required. Default mode (off) preserves current loading
            behaviour for in-tree plugins. GHSA-2rv7 follow-up.
        """
        from version import VERSION, version_meets
        from utils.plugin_signature import gate_plugin_load

        for plugin_id, plugin in self.plugins.items():
            if not plugin.manifest.enabled:
                print(f"  ⏸️  Plugin '{plugin.manifest.name}' is disabled, skipping")
                continue

            # Version gate
            if not version_meets(plugin.manifest.min_redwire_version, VERSION):
                plugin.error = (
                    f"plugin requires RedWire >= {plugin.manifest.min_redwire_version} "
                    f"but this instance is {VERSION}"
                )
                print(f"  ❌ {plugin.manifest.name}: {plugin.error}")
                continue

            # Signature gate
            plugin_dir = Path(self._plugins_dir) / plugin.id
            should_load, reason = gate_plugin_load(plugin_dir, plugin.id)
            if not should_load:
                plugin.error = reason or "signature gate refused load"
                print(f"  ❌ {plugin.manifest.name}: {plugin.error}")
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
                        # RBAC gate — no-op when required_permissions is empty
                        # (the common case). See _make_permission_check.
                        Depends(_make_permission_check(plugin)),
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

    async def get_all_nav_items(self, user=None, db=None) -> list[dict]:
        """Collect nav items from all active plugins, filtered by permissions.

        Each nav_item entry MAY declare its own ``required_permissions``
        list. If a user is supplied, entries the user can't satisfy are
        omitted — otherwise the sidebar would show links that always
        403. The plugin-level ``required_permissions`` list is inherited
        by every nav_item unless the item explicitly overrides.

        Called with ``user=None`` (e.g. an internal caller collecting
        the full catalog) returns everything unfiltered.
        """
        items = []
        # Import lazily so this module stays importable at loader init.
        _has_perm = None
        if user is not None and db is not None:
            from auth.permissions import has_global_permission as _has_perm

        for plugin in self.plugins.values():
            if not (plugin.manifest.enabled and not plugin.error and plugin.has_nav_items):
                continue
            plugin_perms = list(plugin.manifest.required_permissions or [])
            for nav in plugin.manifest.nav_items:
                # Per-item permissions win when present; otherwise fall
                # back to the manifest-level list.
                required = list(nav.get("required_permissions") or plugin_perms)

                if user is not None and required:
                    ok = True
                    for pname in required:
                        try:
                            perm = _resolve_permission(pname)
                        except ValueError:
                            # Unknown permission — hide the item rather
                            # than show a link the user can never use.
                            ok = False
                            break
                        if not await _has_perm(user, perm, db):
                            ok = False
                            break
                    if not ok:
                        continue

                items.append({
                    **nav,
                    "plugin_id": plugin.id,
                    "plugin_name": plugin.manifest.name,
                    "path": nav.get("path", f"/plugins/{plugin.slug}"),
                })
        return items

    async def get_extensions(self, slot: str, user=None, db=None) -> list[dict]:
        """Return every plugin extension registered against ``slot``,
        filtered by the caller's global permissions.

        The frontend passes a slot name (e.g. ``engagement.tabs``) and
        gets back a list of ``{plugin_id, plugin_slug, component, label,
        ...}`` entries it can render. The component name is what the
        generated ``_extensions.generated.tsx`` registry keys on.
        """
        items = []
        _has_perm = None
        if user is not None and db is not None:
            from auth.permissions import has_global_permission as _has_perm

        for plugin in self.plugins.values():
            if not (plugin.manifest.enabled and not plugin.error):
                continue
            plugin_perms = list(plugin.manifest.required_permissions or [])
            for entry in (plugin.manifest.extensions.get(slot) or []):
                if not isinstance(entry, dict):
                    continue
                required = list(entry.get("required_permissions") or plugin_perms)
                if user is not None and required:
                    ok = True
                    for pname in required:
                        try:
                            perm = _resolve_permission(pname)
                        except ValueError:
                            ok = False
                            break
                        if not await _has_perm(user, perm, db):
                            ok = False
                            break
                    if not ok:
                        continue
                items.append({
                    **entry,
                    "plugin_id": plugin.id,
                    "plugin_slug": plugin.slug,
                    "slot": slot,
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
            extensions=data.get("extensions", {}) or {},
            required_permissions=data.get("required_permissions", []),
            enabled=data.get("enabled", True),
        )

    def _load_plugin(self, plugin: LoadedPlugin, app: FastAPI, event_bus, db_factory):
        """Import plugin module and call its setup function.

        GHSA-2rv7-jv5j-m4jg follow-up: loads each plugin as a proper
        Python package via ``spec_from_file_location(...,
        submodule_search_locations=[plugin_dir])`` and does NOT touch
        ``sys.path``. Result: a plugin's internal modules import each
        other as relatives (``from .servicenow import ...``) and
        modules from one plugin can't accidentally satisfy
        ``import x`` in another plugin or in the backend. Plugin
        uninstall fully unloads without a path-cleanup step.

        Bare ``from servicenow import ...`` no longer works — plugin
        authors use relative imports going forward. The two in-tree
        plugins were migrated as part of this commit.
        """
        plugin_dir = Path(self._plugins_dir) / plugin.id
        plugin_dir_str = str(plugin_dir.resolve())
        pkg_name = f"plugins.{plugin.id}"

        # Import __init__.py as a PACKAGE (note submodule_search_locations).
        init_path = plugin_dir / "__init__.py"
        if init_path.exists():
            spec = importlib.util.spec_from_file_location(
                pkg_name,
                str(init_path),
                submodule_search_locations=[plugin_dir_str],
            )
            module = importlib.util.module_from_spec(spec)
            sys.modules[pkg_name] = module
            try:
                spec.loader.exec_module(module)
            except Exception:
                # Best-effort cleanup so a failed exec doesn't leave a
                # half-initialised package in sys.modules to confuse
                # later imports.
                sys.modules.pop(pkg_name, None)
                raise
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
                router_mod_name = f"{pkg_name}.router"
                spec = importlib.util.spec_from_file_location(
                    router_mod_name,
                    str(router_path),
                    submodule_search_locations=[plugin_dir_str],
                )
                router_module = importlib.util.module_from_spec(spec)
                sys.modules[router_mod_name] = router_module
                try:
                    spec.loader.exec_module(router_module)
                except Exception:
                    sys.modules.pop(router_mod_name, None)
                    raise
                if hasattr(router_module, "router"):
                    plugin.router = router_module.router


# Singleton
plugin_registry = PluginRegistry()
