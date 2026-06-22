"""Regression: ``EVIDENCE_EDIT`` is seeded into the right default engagement roles.

When this file was first written, the seeder granted Engagement Lead and
Operator ``EVIDENCE_CREATE`` and ``EVIDENCE_DELETE`` but never
``EVIDENCE_EDIT`` — so a non-admin operator could upload evidence but
could not edit the description, toggle ``include_in_report``, or set a
classification level on their own upload. The PATCH /evidence/{id}
handler requires ``EVIDENCE_EDIT`` (own) or ``EVIDENCE_EDIT_ANY``
(others), so today only admins / hand-granted operators can run that
flow at all.

This test pins the fix: Engagement Lead seeds with both ``EVIDENCE_EDIT``
and ``EVIDENCE_EDIT_ANY`` (matching the EDIT_ANY pattern of FINDING,
NOTE, DISCUSSION, CLEANUP), and Operator seeds with ``EVIDENCE_EDIT``
only (own resources, no _ANY — same pattern as the other Operator
permissions).

Implementation note: the role definitions live as a local variable
inside ``seed_default_groups_and_roles`` (loaded at DB-seed time). To
avoid spinning up a real DB for a contract that's about source content,
we inspect the function's source text and assert each role's literal
block names the right permissions.
"""

from __future__ import annotations

import inspect
import re

import seed_permissions


_SOURCE = inspect.getsource(seed_permissions.seed_default_groups_and_roles)


def _permissions_block_for(role_name: str) -> str:
    """Extract the literal ``permissions=[...]`` block for the named role
    inside the seeder source. Returns the raw text between the role's
    ``"name": "<role_name>"`` line and the next role's name field (or
    end-of-list)."""
    match = re.search(
        rf'"name":\s*"{re.escape(role_name)}".*?"permissions":\s*\[(?P<perms>.*?)\]',
        _SOURCE,
        flags=re.DOTALL,
    )
    if not match:
        raise AssertionError(f"role {role_name!r} not found in seeder source")
    return match.group("perms")


def test_engagement_lead_seeds_evidence_edit_and_edit_any():
    perms = _permissions_block_for("Engagement Lead")
    assert "EVIDENCE_EDIT.value" in perms, (
        "EVIDENCE_EDIT missing from Engagement Lead seed — PATCH /evidence/{id} "
        "is unreachable for engagement leads who aren't also platform admins"
    )
    assert "EVIDENCE_EDIT_ANY.value" in perms, (
        "EVIDENCE_EDIT_ANY missing from Engagement Lead — non-owner edits are "
        "blocked even though the role has EVIDENCE_DELETE_ANY (mismatched scope)"
    )


def test_operator_seeds_evidence_edit_but_not_edit_any():
    perms = _permissions_block_for("Operator")
    assert "EVIDENCE_EDIT.value" in perms, (
        "EVIDENCE_EDIT missing from Operator seed — an operator can upload "
        "evidence (EVIDENCE_CREATE) but can't edit their own metadata"
    )
    # Operator is "own resources only" by design; EDIT_ANY would conflict
    # with the Engagement Lead → Operator scope hierarchy.
    assert "EVIDENCE_EDIT_ANY.value" not in perms, (
        "EVIDENCE_EDIT_ANY granted to Operator — that bypasses the "
        "engagement-lead bottleneck for cross-user evidence edits"
    )


def test_observer_does_not_get_evidence_edit():
    """Observer is read-only by design. If EVIDENCE_EDIT shows up here it's
    almost certainly a copy-paste mistake from one of the other roles."""
    perms = _permissions_block_for("Observer")
    assert "EVIDENCE_EDIT.value" not in perms
    assert "EVIDENCE_EDIT_ANY.value" not in perms
