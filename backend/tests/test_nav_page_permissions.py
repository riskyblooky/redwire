"""Main-nav page permissions: each page's view permission decides whether
the page is offered, and the page-only reads refuse without it."""

from __future__ import annotations

from models.permission import GLOBAL_PERMISSIONS
from tests.test_authz_boundaries import _assign, _make_engagement, _make_engagement_role
from tests.test_security_center import _grant

PAGE_PERMS = ["stats_view", "remediation_view", "template_view", "tag_view", "client_view", "planning_view"]


def test_page_permissions_are_grantable_globals():
    values = {p.value for p in GLOBAL_PERMISSIONS}
    assert set(PAGE_PERMS) <= values


async def test_admins_see_every_page(client, make_user, authenticate_as):
    for role in ("admin", "read_only_admin"):
        authenticate_as(await make_user(role=role))
        held = set((await client.get("/users/me/permissions")).json())
        assert set(PAGE_PERMS) | {"calendar_view", "intel_view", "infra_view", "automation_view"} <= held, role


async def test_effective_list_follows_group_grants(client, db_session, make_user, authenticate_as):
    user = await make_user()
    await _grant(db_session, user, "stats_view")
    authenticate_as(user)
    held = set((await client.get("/users/me/permissions")).json())
    assert "stats_view" in held and "remediation_view" not in held


async def test_remediation_summary_needs_remediation_view(client, db_session, make_user, authenticate_as):
    eng = await _make_engagement(db_session)
    user = await make_user()
    await _assign(db_session, user, eng, await _make_engagement_role(db_session, ["engagement_view", "finding_view"]))
    authenticate_as(user)
    url = f"/findings/remediation-summary?engagement_id={eng.id}"
    assert (await client.get(url)).status_code == 403

    await _grant(db_session, user, "remediation_view")
    assert (await client.get(url)).status_code == 200


async def test_remediation_view_does_not_bypass_engagement_scope(client, db_session, make_user, authenticate_as):
    eng = await _make_engagement(db_session)
    user = await make_user()
    await _grant(db_session, user, "remediation_view")
    authenticate_as(user)
    r = await client.get(f"/findings/remediation-summary?engagement_id={eng.id}")
    assert r.status_code == 403


async def test_stats_pages_need_stats_view(client, db_session, make_user, authenticate_as):
    user = await make_user()
    authenticate_as(user)
    assert (await client.get("/stats-pages")).status_code == 403
    await _grant(db_session, user, "stats_view")
    assert (await client.get("/stats-pages")).status_code == 200


async def test_personal_automations_need_no_permission(client, db_session, make_user, authenticate_as):
    authenticate_as(await make_user())
    assert (await client.get("/automations", params={"scope": "personal"})).status_code == 200
    assert (await client.get("/automations")).status_code == 403
