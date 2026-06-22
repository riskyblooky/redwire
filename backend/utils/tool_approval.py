"""Per-call approval gate for AI write-tool execution.

Backs the Claude-Code-style approve/deny UX in the in-app AI chatbot.
When the LLM proposes a write tool, ``/ai/chat``'s tool-use loop emits
a ``tool_call_pending`` SSE event with a generated ``call_id`` and
blocks on ``wait_for_approval(call_id)``. The chatbot UI renders the
tool name + arguments in an inline card; the user clicks Approve or
Deny; the frontend POSTs to ``/ai/chat/tool-approval/{call_id}``; that
endpoint calls ``record_decision(call_id, decision)``; this module's
wait wakes up and returns.

Implementation: Redis BLPOP on ``redwire:tool_approval:{call_id}``.
The POST endpoint LPUSHes the decision string. Single-consumer
semantics — exactly one waiter, exactly one pusher per call_id.

Fail-closed contract: if Redis is unavailable, the wait returns
``DENY`` immediately. We never silently approve a write because the
approval substrate is down — the user explicitly opted into per-call
confirmation and a broken substrate must default to refusal.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Optional

from auth.jwt import _get_redis

logger = logging.getLogger(__name__)


class ApprovalDecision(str, Enum):
    """The three terminal states of an approval wait."""
    APPROVE = "approve"
    DENY = "deny"
    TIMEOUT = "timeout"


# Redis key shape. Single namespace so the approval queue is easy to
# inspect / flush during incidents.
_KEY_PREFIX = "redwire:tool_approval:"

# 5 minutes — long enough for the user to read the tool name +
# arguments and make a deliberate decision, short enough that a
# forgotten browser tab doesn't hold a backend coroutine forever.
_WAIT_TIMEOUT_SECONDS = 5 * 60


def _key(call_id: str) -> str:
    return f"{_KEY_PREFIX}{call_id}"


def parse_decision(raw: object) -> Optional[ApprovalDecision]:
    """Normalise a Redis BLPOP result (or any caller-supplied value)
    into an ``ApprovalDecision``. Returns ``None`` for inputs that
    aren't a recognised decision string — callers treat that as DENY,
    same as any other fail-closed path.

    Accepts both bytes and str so callers don't have to know whether
    their Redis client returns one or the other.
    """
    if raw is None:
        return None
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except Exception:
            return None
    if not isinstance(raw, str):
        return None
    raw = raw.strip().lower()
    if raw == "approve":
        return ApprovalDecision.APPROVE
    if raw == "deny":
        return ApprovalDecision.DENY
    return None


def record_decision(call_id: str, decision: ApprovalDecision) -> bool:
    """Push a user decision into the queue for the waiting coroutine.

    Returns True on successful publish, False if Redis is unavailable
    or the LPUSH errors. The HTTP endpoint surfaces the boolean so the
    frontend can show "couldn't record decision, please retry" if the
    backend's approval substrate is down.
    """
    if not call_id or not isinstance(call_id, str):
        return False
    r = _get_redis()
    if r is None:
        logger.warning(
            "record_decision: Redis unavailable, can't publish decision "
            "for call_id=%s",
            call_id,
        )
        return False
    try:
        # EXPIRE matches the waiter timeout so a stale queued decision
        # from a never-polled call gets reaped after the waiter would
        # have moved on anyway.
        r.lpush(_key(call_id), decision.value)
        r.expire(_key(call_id), _WAIT_TIMEOUT_SECONDS)
        return True
    except Exception as e:
        logger.warning(
            "record_decision: LPUSH failed for call_id=%s: %s",
            call_id, e,
        )
        return False


def wait_for_approval(
    call_id: str,
    timeout_seconds: int = _WAIT_TIMEOUT_SECONDS,
) -> ApprovalDecision:
    """Block until a decision arrives for ``call_id``, with timeout.

    Fail-closed: Redis unavailable, BLPOP error, unrecognised payload,
    or timeout all return ``DENY``/``TIMEOUT``. The caller must NOT
    execute the underlying tool unless this returns ``APPROVE``.

    This function is *synchronous* because the redis-py client we
    already use is sync. Callers from async paths must run it via
    ``asyncio.to_thread(wait_for_approval, call_id)`` so the BLPOP
    doesn't block the event loop. Documenting this here so reviewers
    catch any direct ``await wait_for_approval(...)`` mistake (which
    wouldn't type-check anyway, but would silently work on a fast
    test path that returns immediately).
    """
    if not call_id or not isinstance(call_id, str):
        logger.warning("wait_for_approval: invalid call_id=%r", call_id)
        return ApprovalDecision.DENY

    r = _get_redis()
    if r is None:
        logger.warning(
            "wait_for_approval: Redis unavailable, denying call_id=%s",
            call_id,
        )
        return ApprovalDecision.DENY

    try:
        result = r.blpop(_key(call_id), timeout=timeout_seconds)
    except Exception as e:
        logger.warning(
            "wait_for_approval: BLPOP failed for call_id=%s: %s",
            call_id, e,
        )
        return ApprovalDecision.DENY

    if result is None:
        # BLPOP timeout — no decision arrived. Treat as a soft denial
        # so the LLM gets a tool-result message it can adapt to,
        # rather than silently executing the write.
        return ApprovalDecision.TIMEOUT

    # BLPOP returns (key, value); the value is what record_decision
    # pushed.
    _key_returned, value = result
    decision = parse_decision(value)
    if decision is None:
        logger.warning(
            "wait_for_approval: unrecognised decision payload for "
            "call_id=%s: %r",
            call_id, value,
        )
        return ApprovalDecision.DENY
    return decision
