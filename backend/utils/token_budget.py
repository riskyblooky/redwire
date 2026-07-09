"""Token-budget-driven conversation compaction for the in-app AI chat.

GHSA-f4j9-gvm9-frjw follow-up. The advisory was closed informational
(cost amplification on an admin-enabled feature with an admin-supplied
key isn't a security boundary), but the right structural fix for the
amplification class is still worth shipping: count tokens against a
configured budget and, when the conversation would push over, slide
a summarization window across the oldest turns instead of letting
input tokens grow unbounded.

Three failure modes this addresses:

  1. Cost — every chat turn today re-uploads the entire prior
     conversation. Long sessions inflate input tokens linearly.
  2. Latency — input tokens dominate response time when histories
     grow large; users notice the spinner.
  3. Prompt-injection amplification — a poisoned tool result (e.g.
     attacker-authored finding description that survives the
     ``_wrap_untrusted`` envelope's structural defense) stays in
     context across every subsequent turn unless explicitly evicted.
     Compaction collapses the prefix into a summary, so a one-shot
     injection's blast radius is bounded by how soon compaction
     fires after it lands.

Compaction strategy: keep the system prompt + the last N turns
exactly as the user sent them; everything in between gets compressed
into a single synthetic assistant message via the same LLM the user
is already chatting with. Per-message tool results that exceed a
secondary threshold get truncated in place before summarization
(large finding lists, attack-graph dumps, etc. are the main
amplification vector and an in-line truncate-with-marker is
something the LLM handles gracefully).

Token estimation: ``count_tokens`` uses a chars/4 heuristic. Slightly
over-counts for English (real ratio ~3.8) — compaction fires a hair
sooner than strictly necessary, which is the safe direction. The
function signature accepts a ``model_hint`` parameter so a future
patch can wire ``tiktoken`` for OpenAI-compat models without
changing callers; the heuristic is the fallback for any provider.

Summary cache: keyed on a SHA-256 of the concatenated source messages.
Same prefix → same summary, no re-LLM-call across turns. Redis-backed
with a 1-hour TTL so a continued conversation reuses the cache and a
finished one expires cheaply. Cache failures are non-fatal (re-runs
the summarization on miss).
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Awaitable, Callable, Optional

import httpx

from auth.jwt import _get_redis

logger = logging.getLogger(__name__)


# Per-tool-result soft cap. Tool calls that return more than this many
# estimated tokens get truncated in place with a marker so the LLM can
# adapt rather than blowing the budget on a single huge payload.
_DEFAULT_PER_TOOL_RESULT_BUDGET = 2000

# Cache TTL — long enough that a paused-then-resumed conversation
# hits the cache, short enough that an abandoned cache entry expires.
_SUMMARY_CACHE_TTL_SECONDS = 60 * 60  # 1 hour

_SUMMARY_CACHE_PREFIX = "ai_chat:summary:"


# ── Token counting ───────────────────────────────────────────────────


def count_tokens(text: str, model_hint: Optional[str] = None) -> int:
    """Estimate the token count of ``text``.

    Uses a chars/4 heuristic — slightly over-counts for English so
    the compaction threshold fires a hair earlier than strictly
    necessary (safe-direction error). ``model_hint`` is accepted for
    future-compatibility with a real tokenizer wire-in (tiktoken for
    OpenAI-compat, anthropic.Anthropic.count_tokens, etc.) without
    changing call sites.
    """
    if not text:
        return 0
    # max(1, ...) so even a one-character message contributes a token
    # of weight to the running tally.
    return max(1, len(text) // 4)


def count_messages_tokens(messages: list[dict], model_hint: Optional[str] = None) -> int:
    """Total token estimate across an OpenAI-shape messages list.

    Counts the role label + content + (if present) tool name +
    arguments + tool_call_id metadata, since each contributes to the
    upstream request body the provider tokenizes.
    """
    total = 0
    for msg in messages:
        # Role and content are the dominant terms.
        total += count_tokens(str(msg.get("role", "")), model_hint)
        content = msg.get("content")
        if isinstance(content, str):
            total += count_tokens(content, model_hint)
        elif isinstance(content, list):
            # Some providers carry list-of-parts content; flatten.
            for part in content:
                if isinstance(part, dict):
                    total += count_tokens(json.dumps(part, default=str), model_hint)
        # tool_calls live on the assistant message when the model
        # asked to call something — their argument JSON does count.
        for tc in (msg.get("tool_calls") or []):
            fn = tc.get("function", {})
            total += count_tokens(fn.get("name", ""), model_hint)
            total += count_tokens(fn.get("arguments", ""), model_hint)
        # tool result messages carry tool_call_id metadata.
        total += count_tokens(str(msg.get("tool_call_id", "")), model_hint)
    return total


# ── Per-tool-result truncation ───────────────────────────────────────


def truncate_tool_result(
    content: str,
    budget_tokens: int = _DEFAULT_PER_TOOL_RESULT_BUDGET,
    model_hint: Optional[str] = None,
) -> str:
    """If ``content`` exceeds the per-tool budget, cut to the budget
    and append a marker so the LLM knows what happened. Returns
    ``content`` unchanged if already under budget.
    """
    if count_tokens(content, model_hint) <= budget_tokens:
        return content
    # chars/4 == tokens/1 → tokens*4 chars roughly bounds us
    char_cap = budget_tokens * 4
    truncated = content[:char_cap]
    return (
        truncated
        + f"\n\n[... tool result truncated to ~{budget_tokens} tokens to fit "
        f"the context budget. Ask for a narrower query if you need more. ...]"
    )


# ── Summary cache ────────────────────────────────────────────────────


def _summary_cache_key(messages: list[dict]) -> str:
    """Stable hash of the messages list. Same content → same key,
    so a continued conversation that includes the same compacted
    prefix reuses the cached summary."""
    serialised = json.dumps(messages, sort_keys=True, default=str)
    digest = hashlib.sha256(serialised.encode("utf-8")).hexdigest()
    return f"{_SUMMARY_CACHE_PREFIX}{digest}"


def _cache_get(key: str) -> Optional[str]:
    r = _get_redis()
    if r is None:
        return None
    try:
        val = r.get(key)
        if val is None:
            return None
        return val.decode("utf-8") if isinstance(val, bytes) else str(val)
    except Exception as e:
        logger.warning("summary cache get failed: %s", e)
        return None


def _cache_set(key: str, value: str) -> None:
    r = _get_redis()
    if r is None:
        return
    try:
        r.set(key, value, ex=_SUMMARY_CACHE_TTL_SECONDS)
    except Exception as e:
        logger.warning("summary cache set failed: %s", e)


# ── Compaction ──────────────────────────────────────────────────────


SummarizerFn = Callable[[list[dict]], Awaitable[str]]


def split_for_compaction(
    messages: list[dict],
    keep_recent_turns: int,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Partition ``messages`` into (system, to_summarize, recent_tail).

    A "turn" is one user message and its associated assistant response
    (plus any tool messages that belong to that response). The
    implementation counts user messages from the end backwards and
    cuts the boundary at the start of the Kth-most-recent user
    message — everything user/assistant/tool from that point forward
    is the tail; everything before is the head to summarize.

    Returns three disjoint lists whose concatenation is the original
    (modulo the implicit ordering invariant: system first, tail last).
    The system messages are pulled out separately because they must
    survive compaction unchanged — the system prompt is what tells
    the model how to behave, dropping it would break the assistant.
    """
    system_msgs: list[dict] = [m for m in messages if m.get("role") == "system"]
    rest: list[dict] = [m for m in messages if m.get("role") != "system"]

    # Find indices of user messages — these are the turn boundaries.
    user_indices = [i for i, m in enumerate(rest) if m.get("role") == "user"]

    if len(user_indices) <= keep_recent_turns:
        # Not enough turns to compact — everything stays as the tail.
        return system_msgs, [], rest

    cut_at = user_indices[-keep_recent_turns]
    to_summarize = rest[:cut_at]
    recent_tail = rest[cut_at:]
    return system_msgs, to_summarize, recent_tail


async def _summarize_via_llm(
    messages: list[dict],
    api_url: str,
    api_key: str,
    model: str,
    tls_verify: bool = True,
) -> str:
    """Single non-streaming LLM call that compresses ``messages`` into
    a short bullet-point summary. Low temperature, explicit instruction
    to preserve IDs / names / decisions so the tail can still reference
    them.

    Returns the summary text. On any failure returns a fallback
    template that lists the message count + roles — the conversation
    still survives, just with a less helpful summary.
    """
    sys_prompt = (
        "You are compressing earlier conversation turns into a short "
        "summary so they fit a token budget. Output 3-8 bullet points "
        "ONLY. Preserve: any UUIDs / IDs, finding titles, asset names, "
        "specific decisions the user made, and questions that are still "
        "open. Omit: pleasantries, repeated context, verbose tool "
        "results. Start with `[Earlier in this conversation:]`."
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": sys_prompt},
            *messages,
            {"role": "user", "content": "Summarize the above per the instructions."},
        ],
        "temperature": 0.2,
        "stream": False,
    }
    try:
        async with httpx.AsyncClient(timeout=60, verify=tls_verify) as client:
            resp = await client.post(
                f"{api_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if resp.status_code != 200:
                logger.warning(
                    "summarizer call failed (%s); falling back to template",
                    resp.status_code,
                )
                return _summary_fallback(messages)
            data = resp.json()
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not text or not isinstance(text, str):
                return _summary_fallback(messages)
            return text.strip()
    except Exception as e:
        logger.warning("summarizer call exception; falling back: %s", e)
        return _summary_fallback(messages)


def _summary_fallback(messages: list[dict]) -> str:
    """Last-resort summary when the LLM call itself fails. Counts
    messages by role so the model at least knows the shape of what
    got dropped."""
    by_role: dict[str, int] = {}
    for m in messages:
        by_role[m.get("role", "?")] = by_role.get(m.get("role", "?"), 0) + 1
    shape = ", ".join(f"{n} {role}" for role, n in by_role.items())
    return (
        f"[Earlier in this conversation: {len(messages)} messages "
        f"({shape}) were compacted but the summarizer was unavailable. "
        f"Ask the user to recap if you need specifics.]"
    )


async def compact_if_needed(
    messages: list[dict],
    max_context_tokens: int,
    keep_recent_turns: int,
    threshold_pct: int,
    api_url: str,
    api_key: str,
    model: str,
    model_hint: Optional[str] = None,
    tls_verify: bool = True,
) -> tuple[list[dict], dict]:
    """If ``messages`` exceeds ``threshold_pct%`` of ``max_context_tokens``,
    compact the head into a summary and return the reduced list.

    Returns ``(new_messages, stats)`` where stats carries the info the
    chat route emits as a ``context_compacted`` SSE event for the UI:
    ``{tokens_before, tokens_after, summarized_count, kept_count,
    fired}``.

    Non-destructive: if the threshold isn't met, returns the input
    unchanged with ``fired=False``. If compaction is enabled but the
    conversation is too short to compact (< keep_recent_turns + 1
    turns), also returns unchanged.
    """
    tokens_before = count_messages_tokens(messages, model_hint)
    threshold_tokens = int(max_context_tokens * threshold_pct / 100)
    stats = {
        "tokens_before": tokens_before,
        "tokens_after": tokens_before,
        "summarized_count": 0,
        "kept_count": len(messages),
        "fired": False,
    }
    if tokens_before <= threshold_tokens:
        return messages, stats

    system_msgs, to_summarize, recent_tail = split_for_compaction(
        messages, keep_recent_turns,
    )
    if not to_summarize:
        # Conversation is shorter than the keep-recent window; nothing
        # to compress. Don't fire compaction.
        return messages, stats

    # Cache lookup keyed on the summarized prefix.
    cache_key = _summary_cache_key(to_summarize)
    summary_text = _cache_get(cache_key)
    if summary_text is None:
        summary_text = await _summarize_via_llm(
            to_summarize, api_url, api_key, model, tls_verify=tls_verify,
        )
        _cache_set(cache_key, summary_text)

    summary_msg = {"role": "assistant", "content": summary_text}
    new_messages = [*system_msgs, summary_msg, *recent_tail]
    tokens_after = count_messages_tokens(new_messages, model_hint)

    stats = {
        "tokens_before": tokens_before,
        "tokens_after": tokens_after,
        "summarized_count": len(to_summarize),
        "kept_count": len(recent_tail),
        "fired": True,
    }
    logger.info(
        "ai-chat compaction fired: %d → %d tokens (%d msgs summarized, %d kept)",
        tokens_before, tokens_after, stats["summarized_count"], stats["kept_count"],
    )
    return new_messages, stats
