"""SAML assertion replay cache (GHSA-68hx-hggg-vrr2 follow-up).

A captured SAML ``<Response>`` is replayable until its
``Conditions/@NotOnOrAfter`` window expires — typically 5 minutes. The
``saml_request_id`` cookie binding shipped by GHSA-68hx already closes
the IdP-initiated and cross-session replay paths, but doesn't address
replay *within* the same SP-initiated flow (an attacker who captures
the POST body before the legitimate user submits it can submit it
themselves first or after).

This module is the gold-standard defense: every assertion is single-
use, keyed on its ``ID`` attribute, claimed atomically against Redis
with a TTL matching the assertion's own expiry. Replays land on the
``NX`` collision and the second submission is rejected.

Required prerequisite to safely re-enabling IdP-initiated SSO — without
the per-request cookie binding to fall back on, the replay cache is
the only thing preventing the captured-assertion attack.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from auth.jwt import _get_redis  # shared Redis access; private import is fine within auth/

logger = logging.getLogger(__name__)

# Redis key prefix for seen-assertion entries.
_KEY_PREFIX = "saml_assertion_seen:"

# Minimum TTL we'll write — guards against assertions whose
# NotOnOrAfter has already passed when we receive them (the SAML
# validator should reject those upstream, but a defensive floor here
# avoids ``ex=0`` errors from redis-py and surfaces an unrealistic-
# window assertion to the caller as a replay-class failure).
_MIN_TTL_SECONDS = 60


def claim_saml_assertion(
    assertion_id: Optional[str],
    not_on_or_after: Optional[datetime],
) -> bool:
    """Atomically claim a SAML assertion ID as seen.

    Returns ``True`` on first claim (caller may proceed with the
    assertion). Returns ``False`` on any of:

      - Redis unavailable — fail closed, can't tell whether this is a
        replay so we refuse the assertion entirely. Mirrors
        ``is_token_blacklisted``'s fail-closed contract.
      - ``assertion_id`` missing or empty — an assertion without an ID
        isn't replay-detectable and shouldn't be trusted; refuse.
      - ``not_on_or_after`` missing or already past — the assertion's
        own expiry should have caused the python3-saml validator to
        reject it upstream; if we still see it here, treat as a
        protocol-error class failure and refuse.
      - The Redis ``SET NX`` returns nil — another ACS handler already
        claimed this assertion ID, this is a replay attempt.

    On exceptions during the Redis call, log and return ``False``
    (fail-closed).
    """
    if not assertion_id or not isinstance(assertion_id, str):
        logger.warning("SAML replay-cache: missing assertion_id, refusing")
        return False

    if not_on_or_after is None:
        logger.warning(
            "SAML replay-cache: assertion %s missing NotOnOrAfter, refusing",
            assertion_id,
        )
        return False

    # Normalise to UTC-naive for arithmetic against utcnow().
    if not_on_or_after.tzinfo is not None:
        not_on_or_after = not_on_or_after.astimezone(timezone.utc).replace(tzinfo=None)

    ttl_seconds = int((not_on_or_after - datetime.utcnow()).total_seconds())
    if ttl_seconds < _MIN_TTL_SECONDS:
        logger.warning(
            "SAML replay-cache: assertion %s NotOnOrAfter window (%ss) "
            "already past or below floor; refusing",
            assertion_id, ttl_seconds,
        )
        return False

    r = _get_redis()
    if r is None:
        logger.critical(
            "SAML replay-cache: Redis unavailable, failing closed on "
            "assertion %s", assertion_id,
        )
        return False

    try:
        # SET key value NX EX ttl — atomic test-and-set. Returns truthy
        # on first claim, falsy on collision (replay).
        claimed = r.set(
            f"{_KEY_PREFIX}{assertion_id}",
            "1",
            nx=True,
            ex=ttl_seconds,
        )
    except Exception as e:
        logger.critical(
            "SAML replay-cache: Redis call failed for assertion %s: %s; "
            "failing closed", assertion_id, e,
        )
        return False

    if not claimed:
        logger.warning(
            "SAML replay-cache: replay detected on assertion %s, refusing",
            assertion_id,
        )
        return False

    return True
