"""The org-rule list shows every org rule to an AUTOMATION_VIEW holder —
the same people who can open (and, with AUTOMATION_EDIT, edit) any of them
by id. Non-admins used to see only the rules they wrote, so another
author's rule could be edited but never found. Personal rules stay private."""

from __future__ import annotations

import uuid


async def test_org_list_matches_single_rule_access(client, db_session, make_user, authenticate_as):
    from models.automation import AutomationRule
    from tests.test_user_manager_ceiling import _group, _join
    viewer = await make_user()
    await _join(db_session, viewer, await _group(db_session, "automation_view"))
    other = await make_user()
    org_rule = AutomationRule(id=str(uuid.uuid4()), name="someone else's", trigger_type="created_finding",
                              created_by=other.id, conditions=[], actions=[], is_enabled=False)
    personal = AutomationRule(id=str(uuid.uuid4()), name="private", trigger_type="created_finding",
                              created_by=other.id, owner_user_id=other.id, conditions=[], actions=[])
    db_session.add_all([org_rule, personal])
    await db_session.flush()
    authenticate_as(viewer)
    ids = {r["id"] for r in (await client.get("/automations")).json()["rules"]}
    assert org_rule.id in ids and personal.id not in ids
    assert (await client.get(f"/automations/{org_rule.id}")).status_code == 200
    assert (await client.get(f"/automations/{personal.id}")).status_code == 404
