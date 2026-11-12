"""Regressions for the "Logic errors" items of the 2026-11 code review."""

from __future__ import annotations

import uuid

import pytest

from models.finding import FindingStatus, Severity
from models.permission import Permission
from tests.test_authz_boundaries import _assign, _make_engagement, _make_engagement_role, _make_finding


@pytest.fixture
def rule_triggers(monkeypatch):
    """Triggers passed to the automation engine (automations run inline in tests)."""
    seen: list[str] = []

    async def _capture(db, trigger, context):
        seen.append(trigger)

    import utils.automation_engine as ae
    monkeypatch.setattr(ae, "evaluate_rules", _capture)
    return seen


# ── GET /findings honours severity and status ──

async def test_finding_list_filters_by_severity_and_status(client, db_session, make_user, authenticate_as):
    eng = await _make_engagement(db_session)
    high = await _make_finding(db_session, eng, severity=Severity.HIGH, status=FindingStatus.OPEN)
    low = await _make_finding(db_session, eng, severity=Severity.LOW, status=FindingStatus.VERIFIED)
    authenticate_as(await make_user(role="admin"))

    def ids(r):
        assert r.status_code == 200, r.text
        return {f["id"] for f in r.json()}

    base = f"/findings?engagement_id={eng.id}"
    assert ids(await client.get(base)) == {high.id, low.id}
    assert ids(await client.get(f"{base}&severity=HIGH")) == {high.id}
    assert ids(await client.get(f"{base}&status=VERIFIED")) == {low.id}
    assert ids(await client.get(f"{base}&severity=HIGH&status=VERIFIED")) == set()


# ── @mentions ──

def test_mention_parsing_keeps_dotted_names_and_skips_emails():
    from utils.collaboration import _mentioned_usernames as m
    assert m("ping @john.doe please") == {"john.doe"}
    assert m("thanks @jane.") == {"jane"}
    assert m("mail alice@example.com") == set()
    assert m("(@Bob_Smith) and @a-b-c,") == {"bob_smith", "a-b-c"}


async def test_dotted_mention_notifies_only_that_user(db_session, make_user, monkeypatch):
    import utils.collaboration as collab
    john = await make_user(username="john")
    john_doe = await make_user(username="john.doe")
    notified = []

    async def _notify(db, user_id, **kw):
        notified.append(user_id)

    monkeypatch.setattr(collab, "create_notification", _notify)
    await collab.notify_mentions(db_session, "hey @john.doe", actor_id=john.id, title="t")
    assert notified == [john_doe.id]


# ── Authors editing their verified finding; approvals vs edits ──

async def _author_with_edit(db_session, make_user, eng):
    author = await make_user(role="operator")
    role = await _make_engagement_role(db_session, [
        Permission.ENGAGEMENT_VIEW.value, Permission.FINDING_VIEW.value, Permission.FINDING_EDIT.value,
    ])
    await _assign(db_session, author, eng, role)
    return author


async def test_author_can_edit_own_verified_finding_but_not_self_attest(client, db_session, make_user, authenticate_as):
    eng = await _make_engagement(db_session)
    author = await _author_with_edit(db_session, make_user, eng)
    verified = await _make_finding(db_session, eng, created_by=author.id, status=FindingStatus.VERIFIED)
    open_one = await _make_finding(db_session, eng, created_by=author.id, status=FindingStatus.OPEN)
    ids = (verified.id, open_one.id)
    db_session.expunge_all()  # the router must load them itself (seeded objects lack eager loads)
    authenticate_as(author)

    # The edit form resends the unchanged status: not a self-attestation.
    r = await client.put(f"/findings/{ids[0]}", json={"title": "Typo fixed", "status": "VERIFIED"})
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "Typo fixed"

    r = await client.put(f"/findings/{ids[1]}", json={"status": "VERIFIED"})
    assert r.status_code == 403, r.text


async def test_content_edit_withdraws_peer_approvals(client, db_session, make_user, authenticate_as):
    from sqlalchemy import select
    from models.finding_review import FindingReview
    eng = await _make_engagement(db_session)
    author = await _author_with_edit(db_session, make_user, eng)
    finding = await _make_finding(db_session, eng, created_by=author.id)
    approver, critic = await make_user(), await make_user()
    db_session.add_all([
        FindingReview(id=str(uuid.uuid4()), finding_id=finding.id, reviewer_id=approver.id, status="APPROVED"),
        FindingReview(id=str(uuid.uuid4()), finding_id=finding.id, reviewer_id=critic.id, status="CHANGES_REQUESTED"),
    ])
    await db_session.flush()
    fid = finding.id
    db_session.expunge_all()
    authenticate_as(author)

    async def verdicts():
        rows = (await db_session.execute(
            select(FindingReview.status).where(FindingReview.finding_id == fid))).scalars().all()
        return sorted(rows)

    # A save that doesn't touch reviewed content keeps the approval.
    assert (await client.put(f"/findings/{fid}", json={"tag_ids": []})).status_code == 200
    assert await verdicts() == ["APPROVED", "CHANGES_REQUESTED"]

    r = await client.put(f"/findings/{fid}", json={"description": "Rewritten after review."})
    assert r.status_code == 200, r.text
    assert await verdicts() == ["CHANGES_REQUESTED"]


# ── Automation triggers that never fired ──

async def test_comment_and_execution_triggers_fire(db_session, rule_triggers):
    from utils.collaboration import create_activity_log
    eng = await _make_engagement(db_session)
    await create_activity_log(db_session, engagement_id=eng.id, user_id=None, action="commented",
                              resource_type="comment", resource_id="c1", resource_name="x")
    await create_activity_log(db_session, engagement_id=eng.id, user_id=None, action="updated_testcase",
                              resource_type="testcase", resource_id="t1", resource_name="x",
                              extra_context={"changes": {"is_executed": {"old": False, "new": True}}})
    # Un-executing is not an execution.
    await create_activity_log(db_session, engagement_id=eng.id, user_id=None, action="updated_testcase",
                              resource_type="testcase", resource_id="t1", resource_name="x",
                              extra_context={"changes": {"is_executed": {"old": True, "new": False}}})
    assert rule_triggers.count("created_comment") == 1
    assert rule_triggers.count("executed_testcase") == 1


async def test_team_changes_fire_assigned_and_removed_user(client, db_session, make_user, authenticate_as, rule_triggers):
    eng = await _make_engagement(db_session)
    member = await make_user(role="operator")
    role = await _make_engagement_role(db_session, [Permission.ENGAGEMENT_VIEW.value])
    authenticate_as(await make_user(role="admin"))

    r = await client.put(f"/engagements/{eng.id}", json={"assignments": [{"user_id": member.id, "role_id": role.id}]})
    assert r.status_code == 200, r.text
    assert rule_triggers.count("assigned_user") == 1 and "removed_user" not in rule_triggers

    # Resaving the same team is not a change.
    r = await client.put(f"/engagements/{eng.id}", json={"assignments": [{"user_id": member.id, "role_id": role.id}]})
    assert r.status_code == 200, r.text
    assert rule_triggers.count("assigned_user") == 1

    r = await client.put(f"/engagements/{eng.id}", json={"assignments": []})
    assert r.status_code == 200, r.text
    assert rule_triggers.count("removed_user") == 1


def test_every_catalog_trigger_has_an_emitter():
    """A rule-editor trigger nothing emits is a rule that silently never runs."""
    import re
    from pathlib import Path
    from models.automation import TRIGGER_TYPES  # noqa: F401  (name checked below)
    src = "\n".join(p.read_text() for p in Path(".").glob("routers/*.py")) + Path("utils/collaboration.py").read_text()
    for trigger in TRIGGER_TYPES:
        if trigger == "manual" or trigger.endswith("_status_changed"):
            continue  # run-now button; status triggers are derived in collaboration.py
        assert re.search(rf'["\']{trigger}["\']', src), f"no code path emits trigger {trigger!r}"
