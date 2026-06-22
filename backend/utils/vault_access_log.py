"""Per-(user, vault-item) reveal-log dedup window.

GHSA-fp69-w2mg-4pqp follow-up. Every call to ``GET /vault/{item_id}/reveal``
and ``GET /vault/download/{item_id}`` writes an ``accessed_vault_secret``
``activity_log`` row so an investigator can later see *which* specific
credentials a departed operator pulled. Pure per-click logging would
drown the signal: a chatty user can rack up dozens of rows per session
per credential by toggling the eye-icon or hitting the copy button
several times.

This module implements the dedup window. The first reveal of a given
``(user_id, item_id)`` pair logs; further reveals inside the window
return ``False`` from :func:`should_log_vault_access` and the caller
skips the log. Five minutes matches the natural "I'm investigating
this credential" intent.

Fail-open contract — the opposite of the SAML replay cache (which
fails closed because we'd accept a bad assertion). Here, Redis being
down means we can't dedup; the safe answer is to log every reveal
rather than silently drop the audit trail. The signal-to-noise hit is
acceptable for the rare-Redis-outage case.
"""

from __future__ import annotations

import logging

from auth.jwt import _get_redis

logger = logging.getLogger(__name__)

_KEY_PREFIX = "vault_access_seen:"
_DEDUP_WINDOW_SECONDS = 5 * 60


def should_log_vault_access(user_id: str, item_id: str) -> bool:
    """Return ``True`` if this reveal should write an activity-log row.

    Atomic SET NX EX against Redis. First call for a ``(user, item)``
    pair returns True and writes the dedup key with a 5-minute TTL.
    Subsequent calls inside the window land on the existing key and
    return False — caller skips the log.

    On Redis outage or any internal error, returns ``True`` (fail
    open: the audit trail is the load-bearing artifact here, so
    over-logging beats under-logging).
    """
    if not user_id or not item_id:
        # No way to dedup without both halves; log defensively.
        return True

    r = _get_redis()
    if r is None:
        logger.warning(
            "vault-access dedup: Redis unavailable, logging without dedup"
        )
        return True

    try:
        claimed = r.set(
            f"{_KEY_PREFIX}{user_id}:{item_id}",
            "1",
            nx=True,
            ex=_DEDUP_WINDOW_SECONDS,
        )
    except Exception as e:
        logger.warning(
            "vault-access dedup: Redis call failed (%s); logging without dedup",
            e,
        )
        return True

    # `claimed` is truthy on first-time set, None on NX collision (replay).
    return bool(claimed)
