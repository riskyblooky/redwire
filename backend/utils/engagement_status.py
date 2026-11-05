"""Allowed engagement status transitions for non-admin users.

Forward any number of stages (but COMPLETED only from REPORTING), back one
stage, and ON_HOLD to/from any open stage. Admins and team leads bypass this;
reopening COMPLETED stays admin/team-lead only via the COMPLETED edit lock.
"""
from models.engagement import EngagementStatus as S

_STAGES = [S.PROPOSED, S.SCOPING, S.PLANNING, S.IN_PROGRESS, S.REPORTING]


def _build() -> dict:
    allowed: dict = {}
    for i, stage in enumerate(_STAGES):
        nxt = set(_STAGES[i + 1:])          # forward, any distance
        if i > 0:
            nxt.add(_STAGES[i - 1])          # back one stage
        nxt.add(S.ON_HOLD)
        allowed[stage] = nxt
    allowed[S.REPORTING].add(S.COMPLETED)
    allowed[S.ON_HOLD] = set(_STAGES)
    allowed[S.COMPLETED] = set()
    return allowed


ALLOWED_TRANSITIONS: dict = _build()


def transition_allowed(old, new) -> bool:
    """True if a non-admin may move an engagement from ``old`` to ``new``.
    Unknown/legacy old values (None) are unrestricted."""
    if old is None or old == new:
        return True
    return S(new) in ALLOWED_TRANSITIONS.get(S(old), set())
