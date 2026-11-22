"""Compaction folds only the new messages into the previous turn's cached
summary instead of re-summarizing the whole growing prefix every turn; a
fallback summary isn't cached; keep_recent_turns=0 still compacts."""

from __future__ import annotations

import pytest

from utils import token_budget
from utils.token_budget import compact_if_needed


@pytest.fixture
def dict_cache(monkeypatch):
    store = {}
    monkeypatch.setattr(token_budget, "_cache_get", store.get)
    monkeypatch.setattr(token_budget, "_cache_set", store.__setitem__)
    return store


def _convo(turns):
    msgs = [{"role": "system", "content": "sys"}]
    for i in range(turns):
        msgs += [{"role": "user", "content": f"u{i} " + "x" * 100},
                 {"role": "assistant", "content": f"a{i} " + "y" * 100}]
    return msgs


async def _compact(msgs, keep=2):
    return await compact_if_needed(msgs, max_context_tokens=200, keep_recent_turns=keep, threshold_pct=50,
                                   api_url="http://nope", api_key="k", model="m")


async def test_each_turn_summarizes_only_what_is_new(dict_cache, monkeypatch):
    sources = []

    async def fake(messages, *a, **kw):
        sources.append(messages)
        return f"[summary #{len(sources)}]"
    monkeypatch.setattr(token_budget, "_summarize_via_llm", fake)

    for turns in range(4, 12):
        await _compact(_convo(turns))
    # First compaction sees the whole head; every later one sees the previous
    # summary plus one new turn (user + assistant), not the full prefix.
    assert len(sources[0]) == 4
    for i, src in enumerate(sources[1:], start=1):
        assert len(src) == 3, len(src)
        assert src[0] == {"role": "assistant", "content": f"[summary #{i}]"}


async def test_same_prefix_within_a_turn_is_a_cache_hit(dict_cache, monkeypatch):
    calls = []

    async def fake(messages, *a, **kw):
        calls.append(1)
        return "[s]"
    monkeypatch.setattr(token_budget, "_summarize_via_llm", fake)
    msgs = _convo(6)
    await _compact(msgs)
    await _compact(msgs + [{"role": "tool", "content": "z" * 50, "tool_call_id": "t"}])  # a tool round
    assert len(calls) == 1


async def test_fallback_summary_is_not_cached(dict_cache, monkeypatch):
    calls = []

    async def failing(messages, *a, **kw):
        calls.append(1)
        return token_budget._summary_fallback(messages)
    monkeypatch.setattr(token_budget, "_summarize_via_llm", failing)
    msgs = _convo(6)
    await _compact(msgs)
    await _compact(msgs)
    assert len(calls) == 2 and dict_cache == {}


async def test_keep_zero_still_compacts(dict_cache, monkeypatch):
    async def fake(messages, *a, **kw):
        return "[s]"
    monkeypatch.setattr(token_budget, "_summarize_via_llm", fake)
    result, stats = await _compact(_convo(6), keep=0)
    assert stats["fired"] and result[-2]["role"] == "user"   # the current turn survives


def test_local_cache_without_redis(monkeypatch):
    monkeypatch.setattr(token_budget, "_get_redis", lambda: None)
    monkeypatch.setattr(token_budget, "_LOCAL_CACHE", {})
    token_budget._cache_set("k", "v")
    assert token_budget._cache_get("k") == "v"
