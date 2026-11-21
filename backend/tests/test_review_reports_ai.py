"""Regressions for the 2026-11 review's medium items in reports, AI
settings, search and dashboard widgets."""

from __future__ import annotations

import pytest


async def test_ai_compaction_settings_round_trip(client, make_user, authenticate_as):
    authenticate_as(await make_user(role="admin"))
    put = await client.put("/ai/settings", json={
        "ai_max_context_tokens": "32000", "ai_compact_keep_recent_turns": "6", "ai_compact_threshold_pct": "60"})
    assert put.status_code == 200, put.text

    got = (await client.get("/ai/settings")).json()
    assert (got["ai_max_context_tokens"], got["ai_compact_keep_recent_turns"], got["ai_compact_threshold_pct"]) \
        == ("32000", "6", "60")
