"""Regressions for the min_redwire_version comparator and the
event_bus toggle-off subscriber gate.

GHSA-2rv7 and GHSA-4jrh-3m3r-p448 follow-ups. These two pieces are
small but load-bearing: the version comparator decides whether a
plugin authored against a future API loads at all; the event-bus
gate decides whether a TOGGLED-OFF plugin's listeners still fire on
internal events (the route-gate already handles the HTTP surface).
"""

from __future__ import annotations

import asyncio

import pytest

from utils.event_bus import EventBus
from version import VERSION, version_meets


# ── version comparator ───────────────────────────────────────────────


@pytest.mark.parametrize("required, current, expected", [
    ("1.0.0", "1.0.0", True),
    ("1.0.0", "1.0.1", True),
    ("1.0.0", "2.0.0", True),
    ("1.0.1", "1.0.0", False),
    ("2.0.0", "1.9.9", False),
    ("1.5.0", "1.5.0", True),
    ("0.0.0", "1.0.0", True),
    # Multi-part versions
    ("1.2.3.4", "1.2.3.4", True),
    ("1.2.3.4", "1.2.3.5", True),
    ("1.2.3.5", "1.2.3.4", False),
    # Non-integer components fall back to 0 (rc/beta tags)
    ("1.2.3-rc1", "1.2.3", True),  # rc1 → 0, both compare as (1,2,3,0)
])
def test_version_meets(required, current, expected):
    assert version_meets(required, current) is expected


def test_version_constant_is_a_string():
    """If VERSION ever becomes a tuple or None this test catches it
    before the plugin loader's str() coercion silently masks the
    breakage."""
    assert isinstance(VERSION, str)
    assert len(VERSION.split(".")) >= 2  # at least major.minor


# ── EventBus toggle-off gate ─────────────────────────────────────────


def test_handler_with_no_owning_plugin_always_fires():
    """Core-code subscribers (no plugin_id) must NEVER be gated by
    the plugin-enabled check — otherwise the bus stops working for
    non-plugin code."""
    bus = EventBus()
    seen = []

    async def core_handler(event):
        seen.append(event["type"])

    bus.register("asset.created", core_handler)
    # Deliberately leave the enabled predicate at its default.

    asyncio.get_event_loop().run_until_complete(
        bus.emit("asset.created", {"x": 1})
    )
    assert seen == ["asset.created"]


def test_handler_owned_by_enabled_plugin_fires():
    bus = EventBus()
    seen = []

    async def plugin_handler(event):
        seen.append("fired")

    bus.register("asset.created", plugin_handler, plugin_id="my_plugin")
    bus.set_plugin_enabled_check(lambda pid: True)

    asyncio.get_event_loop().run_until_complete(
        bus.emit("asset.created", {})
    )
    assert seen == ["fired"]


def test_handler_owned_by_disabled_plugin_does_not_fire():
    """The actual contract — toggling a plugin off must stop its
    listeners from running on internal events."""
    bus = EventBus()
    seen = []

    async def plugin_handler(event):
        seen.append("fired")

    bus.register("asset.created", plugin_handler, plugin_id="my_plugin")
    bus.set_plugin_enabled_check(lambda pid: False)

    asyncio.get_event_loop().run_until_complete(
        bus.emit("asset.created", {})
    )
    assert seen == []


def test_predicate_consulted_per_emit_so_toggle_takes_immediate_effect():
    """The route-gate's invariant: a toggle-off / toggle-on flip
    must take effect immediately, without re-registering subscribers.
    Mirror that here — the predicate is consulted on every emit, so
    flipping the underlying flag changes behaviour at the next call."""
    bus = EventBus()
    seen = []

    async def plugin_handler(event):
        seen.append(event["type"])

    bus.register("e", plugin_handler, plugin_id="p")
    state = {"enabled": True}
    bus.set_plugin_enabled_check(lambda pid: state["enabled"])

    asyncio.get_event_loop().run_until_complete(bus.emit("e", {}))
    assert seen == ["e"]

    state["enabled"] = False  # toggle off
    asyncio.get_event_loop().run_until_complete(bus.emit("e", {}))
    assert seen == ["e"]  # unchanged — disabled handler skipped

    state["enabled"] = True  # toggle back on
    asyncio.get_event_loop().run_until_complete(bus.emit("e", {}))
    assert seen == ["e", "e"]


def test_unregister_plugin_cleans_handler_owner_map():
    """After unregister_plugin, the handler shouldn't linger in the
    ownership index — otherwise stale entries accumulate across
    multiple install/uninstall cycles."""
    bus = EventBus()

    async def handler(event):
        pass

    bus.register("e", handler, plugin_id="p")
    assert id(handler) in bus._handler_owner

    bus.unregister_plugin("p")
    assert id(handler) not in bus._handler_owner
    # And the main handler list is also cleared.
    assert bus._handlers["e"] == []


def test_mixed_owners_only_disabled_one_is_gated():
    """Two plugins both subscribe; disabling only one should leave
    the other firing."""
    bus = EventBus()
    seen = []

    async def h_a(event):
        seen.append("a")

    async def h_b(event):
        seen.append("b")

    bus.register("e", h_a, plugin_id="plugin_a")
    bus.register("e", h_b, plugin_id="plugin_b")
    bus.set_plugin_enabled_check(lambda pid: pid == "plugin_b")

    asyncio.get_event_loop().run_until_complete(bus.emit("e", {}))
    assert seen == ["b"]
