"""
Event Bus — Lightweight async pub/sub for the plugin system.

Plugins register handlers for event types like 'asset.created', 'finding.updated', etc.
Events are dispatched from create_activity_log() in collaboration.py.

Usage:
    event_bus = EventBus()

    # Plugin registers a handler
    @event_bus.on("asset.created")
    async def handle_asset(event):
        print(f"Asset created: {event['resource_name']}")

    # Core code emits events
    await event_bus.emit("asset.created", {
        "resource_id": "abc-123",
        "resource_name": "10.0.0.1",
        "engagement_id": "eng-456",
        "user_id": "user-789",
    })
"""

import asyncio
import logging
import os
import traceback
from collections import defaultdict
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

# Plugin handlers run as background tasks (see emit), each bounded by this.
PLUGIN_HANDLER_TIMEOUT_S = float(os.getenv("PLUGIN_HANDLER_TIMEOUT_S", "30"))


class EventBus:
    """Async event bus with wildcard support."""

    def __init__(self):
        self._handlers: dict[str, list[Callable]] = defaultdict(list)
        self._plugin_handlers: dict[str, list[tuple[str, Callable]]] = defaultdict(list)
        # Reverse lookup: handler → owning plugin_id. Populated when
        # the handler is registered via ``on()`` / ``register()`` with
        # a plugin_id. Used at emit time by the enabled-gate (below)
        # so a disabled plugin's subscribers don't fire — mirrors the
        # route-gate pattern from plugin_loader.mount_routes.
        # GHSA-4jrh-3m3r-p448 follow-up.
        self._handler_owner: dict[int, str] = {}
        # Injected predicate: ``plugin_id -> bool`` (True = enabled).
        # Set by main.py at startup so the bus doesn't have to import
        # ``plugin_registry`` (which would be circular through
        # plugin loader → setup() → event_bus). Default to "everyone
        # enabled" so non-plugin handlers (core code, tests) keep
        # firing without any setup.
        self._enabled_check: Callable[[str], bool] = lambda _pid: True
        # In-flight plugin handler tasks — held so they aren't garbage
        # collected mid-run, and so drain() can wait for them.
        self._pending: set[asyncio.Task] = set()

    def set_plugin_enabled_check(self, predicate: Callable[[str], bool]) -> None:
        """Wire the per-plugin enabled predicate. Called once at
        startup with a closure over the live plugin_registry; the
        closure reads ``manifest.enabled`` on every dispatch so the
        admin toggle takes effect immediately, no re-subscribe.
        GHSA-4jrh-3m3r-p448 follow-up."""
        self._enabled_check = predicate

    def on(self, event_type: str, plugin_id: str | None = None):
        """Decorator to register a handler for an event type.

        Supports wildcards: 'asset.*' matches 'asset.created', 'asset.updated', etc.
        """
        def decorator(func: Callable[..., Coroutine]):
            self._handlers[event_type].append(func)
            if plugin_id:
                self._plugin_handlers[plugin_id].append((event_type, func))
                self._handler_owner[id(func)] = plugin_id
            return func
        return decorator

    def register(self, event_type: str, handler: Callable, plugin_id: str | None = None):
        """Imperative registration (non-decorator)."""
        self._handlers[event_type].append(handler)
        if plugin_id:
            self._plugin_handlers[plugin_id].append((event_type, handler))
            self._handler_owner[id(handler)] = plugin_id

    def unregister_plugin(self, plugin_id: str):
        """Remove all handlers registered by a specific plugin."""
        for event_type, handler in self._plugin_handlers.pop(plugin_id, []):
            try:
                self._handlers[event_type].remove(handler)
            except ValueError:
                pass
            self._handler_owner.pop(id(handler), None)

    async def emit(self, event_type: str, data: dict[str, Any]):
        """Fire all handlers for exact match + wildcard patterns.

        GHSA-4jrh-3m3r-p448 follow-up: subscribers owned by a plugin
        whose ``enabled`` flag is False are filtered out here so a
        toggle-off via ``PUT /plugins/{id}/toggle`` actually silences
        the plugin's event reactions (previously the routes went 503
        but the listeners kept firing). Core-code subscribers (no
        owning plugin_id) always fire.
        """
        handlers = list(self._handlers.get(event_type, []))

        # Check wildcard handlers (e.g. 'asset.*' matches 'asset.created')
        parts = event_type.split(".")
        if len(parts) >= 2:
            wildcard = f"{parts[0]}.*"
            handlers.extend(self._handlers.get(wildcard, []))

        # Global wildcard
        handlers.extend(self._handlers.get("*", []))

        # Split core subscribers from plugin ones, dropping subscribers
        # whose owning plugin is currently toggled off.
        core, plugin = [], []
        for h in handlers:
            owner = self._handler_owner.get(id(h))
            if owner is None:
                core.append(h)
            elif self._enabled_check(owner):
                plugin.append((owner, h))

        # Plugin handlers run off the request path: emit() is awaited inside
        # create / update requests, and a slow integration (Shodan
        # auto-enrich: up to 10s per lookup) held every asset save hostage.
        # Each runs as its own task with a timeout; handlers open their own
        # DB sessions, so nothing here depends on the caller's.
        for owner, h in plugin:
            task = asyncio.create_task(self._run_plugin_handler(owner, h, event_type, dict(data)))
            self._pending.add(task)
            task.add_done_callback(self._pending.discard)

        # Core subscribers keep the inline contract (callers rely on them).
        if core:
            results = await asyncio.gather(
                *[self._safe_call(h, event_type, data) for h in core],
                return_exceptions=True,
            )
            for r in results:
                if isinstance(r, Exception):
                    print(f"[EventBus] Handler error on '{event_type}': {r}")

    async def _run_plugin_handler(self, owner: str, handler: Callable, event_type: str, data: dict):
        try:
            await asyncio.wait_for(self._safe_call(handler, event_type, data), PLUGIN_HANDLER_TIMEOUT_S)
        except asyncio.TimeoutError:
            logger.warning("EventBus: plugin %s handler for %r timed out after %ss",
                           owner, event_type, PLUGIN_HANDLER_TIMEOUT_S)
        except Exception as e:
            logger.warning("EventBus: plugin %s handler error on %r: %s", owner, event_type, e)

    async def drain(self, timeout: float | None = None) -> None:
        """Wait for in-flight plugin handlers (tests; graceful shutdown)."""
        if self._pending:
            await asyncio.wait(set(self._pending), timeout=timeout)

    @staticmethod
    async def _safe_call(handler: Callable, event_type: str, data: dict):
        try:
            await handler({"type": event_type, **data})
        except Exception as e:
            traceback.print_exc()
            raise

    @property
    def handler_count(self) -> int:
        return sum(len(v) for v in self._handlers.values())

    def registered_events(self) -> list[str]:
        return sorted(self._handlers.keys())


# Singleton instance
event_bus = EventBus()
