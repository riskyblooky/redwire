"""trigger_count is incremented in SQL, so overlapping runs don't lose
increments; ActionSchema no longer carries the unused `body` field."""

from __future__ import annotations

import uuid

from sqlalchemy import select


async def test_trigger_count_increments_in_sql(client, db_session, make_user, authenticate_as):
    from models.automation import AutomationRule
    from utils.automation_engine import execute_rule_actions
    admin = await make_user(role="admin")
    rule = AutomationRule(id=str(uuid.uuid4()), name="r", trigger_type="created_finding", created_by=admin.id,
                          conditions=[], actions=[], trigger_count=5)
    db_session.add(rule)
    await db_session.flush()
    # Another worker bumps the row behind this session's back.
    from sqlalchemy import update
    await db_session.execute(update(AutomationRule).where(AutomationRule.id == rule.id).values(trigger_count=9))
    await execute_rule_actions(db_session, rule, {"action": "manual"})
    await db_session.flush()
    count = (await db_session.execute(select(AutomationRule.trigger_count).where(AutomationRule.id == rule.id))).scalar_one()
    assert count == 10  # 9 + 1, not the stale 5 + 1

    authenticate_as(admin)
    r = await client.post(f"/automations/{rule.id}/run")
    assert r.status_code == 200, r.text
    assert r.json()["trigger_count"] == 11


def test_action_schema_has_no_body():
    from routers.automations import ActionSchema
    assert "body" not in ActionSchema.model_fields
    assert ActionSchema(type="email", body="x", body_template="t").body_template == "t"
