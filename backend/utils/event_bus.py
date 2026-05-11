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
import traceback
from collections import defaultdict
from typing import Any, Callable, Coroutine


class EventBus:
    """Async event bus with wildcard support."""

    def __init__(self):
        self._handlers: dict[str, list[Callable]] = defaultdict(list)
        self._plugin_handlers: dict[str, list[tuple[str, Callable]]] = defaultdict(list)

    def on(self, event_type: str, plugin_id: str | None = None):
        """Decorator to register a handler for an event type.

        Supports wildcards: 'asset.*' matches 'asset.created', 'asset.updated', etc.
        """
        def decorator(func: Callable[..., Coroutine]):
            self._handlers[event_type].append(func)
            if plugin_id:
                self._plugin_handlers[plugin_id].append((event_type, func))
            return func
        return decorator

    def register(self, event_type: str, handler: Callable, plugin_id: str | None = None):
        """Imperative registration (non-decorator)."""
        self._handlers[event_type].append(handler)
        if plugin_id:
            self._plugin_handlers[plugin_id].append((event_type, handler))

    def unregister_plugin(self, plugin_id: str):
        """Remove all handlers registered by a specific plugin."""
        for event_type, handler in self._plugin_handlers.pop(plugin_id, []):
            try:
                self._handlers[event_type].remove(handler)
            except ValueError:
                pass

    async def emit(self, event_type: str, data: dict[str, Any]):
        """Fire all handlers for exact match + wildcard patterns."""
        handlers = list(self._handlers.get(event_type, []))

        # Check wildcard handlers (e.g. 'asset.*' matches 'asset.created')
        parts = event_type.split(".")
        if len(parts) >= 2:
            wildcard = f"{parts[0]}.*"
            handlers.extend(self._handlers.get(wildcard, []))

        # Global wildcard
        handlers.extend(self._handlers.get("*", []))

        if not handlers:
            return

        # Fire all handlers concurrently, don't let one failure kill others
        results = await asyncio.gather(
            *[self._safe_call(h, event_type, data) for h in handlers],
            return_exceptions=True,
        )
        for r in results:
            if isinstance(r, Exception):
                print(f"[EventBus] Handler error on '{event_type}': {r}")

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
