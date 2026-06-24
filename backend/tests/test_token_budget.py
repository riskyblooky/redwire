"""Regressions for the AI-chat token-budget compactor.

GHSA-f4j9-gvm9-frjw follow-up. The chat router calls
``compact_if_needed`` on every tool-use round; the pure logic — token
counting, split partition, threshold trigger, fail-safe summary —
needs to be deterministic across the cases that drive compaction in
the live loop. These tests pin every branch that could silently let
the conversation grow unbounded (the original amplification class)
or, conversely, fire compaction when it shouldn't (which would drop
context the user expects to be preserved).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils import token_budget
from utils.token_budget import (
    _summary_cache_key,
    compact_if_needed,
    count_messages_tokens,
    count_tokens,
    split_for_compaction,
    truncate_tool_result,
)


# ── count_tokens ────────────────────────────────────────────────────


@pytest.mark.parametrize("text, expected", [
    ("", 0),
    ("a", 1),       # max(1, 1//4) = 1
    ("abcd", 1),    # max(1, 4//4) = 1
    ("a" * 8, 2),   # 8//4 = 2
    ("a" * 400, 100),
])
def test_count_tokens_chars_over_four(text, expected):
    """The estimator is chars/4 with a floor of 1 for any non-empty
    string. Pinned so a future tokenizer wire-in doesn't silently
    change the floor (which would shift the threshold trigger)."""
    assert count_tokens(text) == expected


def test_count_messages_tokens_walks_role_content_tool_calls():
    """count_messages_tokens has to walk every place tokens accrue —
    role label, content, tool_calls function name + arguments,
    tool_call_id. If any of those gets missed the live token tally
    under-counts and compaction fires later than it should."""
    messages = [
        {"role": "system", "content": "a" * 100},  # 100/4 = 25
        {"role": "user", "content": "b" * 200},    # 200/4 = 50
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": "x",
                "function": {"name": "list_findings", "arguments": '{"engagement_id":"abc"}'},
            }],
        },
        {"role": "tool", "tool_call_id": "x", "content": "c" * 80},  # 80/4 = 20
    ]
    total = count_messages_tokens(messages)
    # Should at minimum count the three big content blocks + the
    # tool-call arguments (~30 chars/4 + role labels + ids). Pin a
    # lower bound rather than the exact figure so the test survives
    # small tweaks to which fields the helper visits.
    assert total >= 100


# ── truncate_tool_result ─────────────────────────────────────────────


def test_truncate_tool_result_passes_through_when_small():
    """A small payload shouldn't get the truncation marker appended —
    the marker is itself a token cost we don't want to pay
    unnecessarily."""
    payload = "x" * 200
    assert truncate_tool_result(payload, budget_tokens=2000) == payload


def test_truncate_tool_result_cuts_with_marker_when_huge():
    """50 KB tool result against a 2000-token budget gets cut roughly
    to budget*4 chars + the human-readable marker. The marker is the
    contract that the LLM uses to know it can ask a narrower query."""
    payload = "x" * 50_000
    out = truncate_tool_result(payload, budget_tokens=2000)
    assert len(out) < len(payload)
    assert "tool result truncated" in out
    assert "narrower query" in out


# ── split_for_compaction ─────────────────────────────────────────────


def _build_convo(num_turns: int) -> list[dict]:
    """Build [system, (user, assistant) × num_turns] — the simplest
    shape that exercises the split logic."""
    msgs = [{"role": "system", "content": "you are helpful"}]
    for i in range(num_turns):
        msgs.append({"role": "user", "content": f"user msg {i}"})
        msgs.append({"role": "assistant", "content": f"reply {i}"})
    return msgs


def test_split_keeps_system_separate():
    msgs = _build_convo(6)
    system, to_summarize, tail = split_for_compaction(msgs, keep_recent_turns=2)
    assert system == [{"role": "system", "content": "you are helpful"}]
    assert {m["role"] for m in system} == {"system"}


def test_split_keeps_last_k_user_turns_in_tail():
    """The cut boundary is at the start of the K-th-most-recent USER
    message — so the tail must contain K user messages and their
    associated assistant replies."""
    msgs = _build_convo(6)
    _system, _to_summarize, tail = split_for_compaction(msgs, keep_recent_turns=2)
    user_in_tail = sum(1 for m in tail if m["role"] == "user")
    assert user_in_tail == 2


def test_split_returns_empty_to_summarize_for_short_convo():
    """If there are fewer turns than keep_recent_turns, nothing should
    be summarized — compaction must be a no-op."""
    msgs = _build_convo(2)
    _system, to_summarize, tail = split_for_compaction(msgs, keep_recent_turns=4)
    assert to_summarize == []
    # Tail should be the whole non-system tail.
    assert all(m["role"] != "system" for m in tail)


def test_split_includes_tool_messages_in_their_turn():
    """A real tool-use turn is user → assistant(tool_calls) → tool → assistant.
    The split partitions on user-message indices, so the tool +
    final-assistant for a kept user should land in the tail with it."""
    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "turn 0"},
        {"role": "assistant", "content": "r0"},
        {"role": "user", "content": "turn 1"},
        {"role": "assistant", "tool_calls": [{"id": "x", "function": {"name": "f", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "x", "content": "data"},
        {"role": "assistant", "content": "r1"},
    ]
    _system, to_summarize, tail = split_for_compaction(msgs, keep_recent_turns=1)
    # Only turn 0 should be summarized.
    assert any(m.get("content") == "turn 0" for m in to_summarize)
    # The whole turn 1 (user + tool round + final reply) should be in tail.
    assert any(m.get("content") == "turn 1" for m in tail)
    assert any(m.get("role") == "tool" for m in tail)


# ── compact_if_needed ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_compact_below_threshold_is_noop():
    """Short conversation under the threshold — must NOT fire
    compaction. Returns the input unchanged with fired=False."""
    msgs = _build_convo(3)
    result, stats = await compact_if_needed(
        msgs,
        max_context_tokens=8000,
        keep_recent_turns=4,
        threshold_pct=75,
        api_url="http://nope", api_key="k", model="gpt-4",
    )
    assert result == msgs
    assert stats["fired"] is False
    assert stats["summarized_count"] == 0


@pytest.mark.asyncio
async def test_compact_above_threshold_fires_and_replaces_prefix(monkeypatch):
    """The trigger path — long convo over threshold goes through the
    summarizer, swaps prefix for the summary, preserves system + tail."""
    # Build a conversation big enough to exceed 75% of 200 tokens
    # (i.e. > 150 tokens). 8 turns at ~25 chars each = ~200 tokens.
    msgs = []
    msgs.append({"role": "system", "content": "sys"})
    for i in range(10):
        msgs.append({"role": "user", "content": "u" * 100})
        msgs.append({"role": "assistant", "content": "a" * 100})

    # Stub the summarizer to avoid a real HTTP call.
    async def fake_summarize(messages, api_url, api_key, model):
        return "[Earlier: stub summary]"

    monkeypatch.setattr(token_budget, "_summarize_via_llm", fake_summarize)
    monkeypatch.setattr(token_budget, "_cache_get", lambda key: None)
    monkeypatch.setattr(token_budget, "_cache_set", lambda key, value: None)

    result, stats = await compact_if_needed(
        msgs,
        max_context_tokens=200,
        keep_recent_turns=2,
        threshold_pct=75,
        api_url="http://nope", api_key="k", model="gpt-4",
    )
    assert stats["fired"] is True
    assert stats["summarized_count"] > 0
    assert stats["tokens_after"] < stats["tokens_before"]
    # System must survive at index 0.
    assert result[0]["role"] == "system"
    # The summary should be the second message.
    assert result[1]["content"] == "[Earlier: stub summary]"


@pytest.mark.asyncio
async def test_compact_uses_cached_summary_when_available(monkeypatch):
    """Same source prefix → cache hit → no LLM call. Critical for
    cost — without this every tool-use round inside one chat turn
    would re-summarize the same head."""
    msgs = [{"role": "system", "content": "sys"}]
    for i in range(8):
        msgs.append({"role": "user", "content": "u" * 100})
        msgs.append({"role": "assistant", "content": "a" * 100})

    fake_summarizer = AsyncMock(return_value="(should not be called)")
    monkeypatch.setattr(token_budget, "_summarize_via_llm", fake_summarizer)
    monkeypatch.setattr(token_budget, "_cache_get", lambda key: "[cached summary]")
    monkeypatch.setattr(token_budget, "_cache_set", lambda key, value: None)

    result, stats = await compact_if_needed(
        msgs,
        max_context_tokens=200,
        keep_recent_turns=2,
        threshold_pct=75,
        api_url="http://nope", api_key="k", model="gpt-4",
    )
    assert stats["fired"] is True
    fake_summarizer.assert_not_awaited()
    assert any(m.get("content") == "[cached summary]" for m in result)


@pytest.mark.asyncio
async def test_compact_handles_short_convo_above_threshold(monkeypatch):
    """A short-but-bloated conversation (e.g. one massive user message)
    can be over the threshold even though it has fewer turns than the
    keep-recent window. Must return a no-op rather than crash — there's
    nothing safe to summarize."""
    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "u" * 10_000},
        {"role": "assistant", "content": "a" * 100},
    ]
    fake_summarizer = AsyncMock(return_value="should not be called")
    monkeypatch.setattr(token_budget, "_summarize_via_llm", fake_summarizer)

    result, stats = await compact_if_needed(
        msgs,
        max_context_tokens=100,
        keep_recent_turns=4,  # > the 1 user turn we have
        threshold_pct=75,
        api_url="http://nope", api_key="k", model="gpt-4",
    )
    assert stats["fired"] is False
    fake_summarizer.assert_not_awaited()
    assert result == msgs


# ── summary cache keying ─────────────────────────────────────────────


def test_summary_cache_key_is_stable_for_same_input():
    """Same messages → same key. Otherwise the cache is useless."""
    msgs = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
    assert _summary_cache_key(msgs) == _summary_cache_key(msgs)


def test_summary_cache_key_changes_when_content_changes():
    a = [{"role": "user", "content": "hi"}]
    b = [{"role": "user", "content": "hello"}]
    assert _summary_cache_key(a) != _summary_cache_key(b)
