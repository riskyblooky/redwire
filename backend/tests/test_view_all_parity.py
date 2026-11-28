"""VIEW_ALL_ENGAGEMENTS reads like a member. Every GET route scoped to one
engagement — an {engagement_id} path parameter as its only path parameter, or
an engagement_id query parameter — is called by three users:

  * a member whose engagement role holds exactly VIEW_ALL_ENGAGEMENT_GRANTS,
  * a user with the global VIEW_ALL_ENGAGEMENTS grant and no assignment,
  * a user with neither.

The first two must get the same status and the same body; the outsider must
never get a 200 that contains the engagement's data. Routes are discovered
from the app, so a new engagement-scoped endpoint is covered without editing
this test."""

from __future__ import annotations

import json
import uuid

from fastapi.routing import APIRoute

from tests.test_authz_boundaries import _assign, _make_engagement, _make_engagement_role, _make_finding
from tests.test_view_all_engagements import _view_all_user

# Responses that describe the caller, or a global admin view keyed by an
# engagement id (gated on the global permission itself, not a read of it).
CALLER_SPECIFIC = {
    "/engagements/{engagement_id}/my-permissions",
    "/admin/deleted-engagement-logs/{engagement_id}",
}
# Keys that differ by caller (their own assignments) or by request time.
IGNORE_KEYS = {
    "/analytics/dashboard-stats": {"my_engagements", "personal_stats"},
    "/stats/findings-timeline": {"start_date", "end_date"},
}


def _routes():
    import main

    out = []
    for r in main.app.routes:
        if not isinstance(r, APIRoute) or "GET" not in r.methods or r.path in CALLER_SPECIFIC:
            continue
        path_params = {p.name for p in r.dependant.path_params}
        query_params = {p.name for p in r.dependant.query_params}
        if path_params == {"engagement_id"}:
            out.append(("path", r.path))
        elif not path_params and "engagement_id" in query_params:
            out.append(("query", r.path))
    return sorted(set(out))


def _url(kind, path, eid):
    return path.replace("{engagement_id}", eid) if kind == "path" else f"{path}?engagement_id={eid}"


async def _seed(db):
    from models.asset import Asset
    from models.cleanup_artifact import CleanupArtifact
    from models.note import Note
    from models.testcase import TestCase

    eng = await _make_engagement(db)
    f = await _make_finding(db, eng)
    marker = f"parity-{uuid.uuid4().hex[:8]}"
    db.add_all([
        Asset(id=str(uuid.uuid4()), engagement_id=eng.id, name=marker, identifier="10.9.9.9", asset_type="host"),
        TestCase(id=str(uuid.uuid4()), engagement_id=eng.id, title=marker, category="c", description="d"),
        CleanupArtifact(id=str(uuid.uuid4()), engagement_id=eng.id, title=marker, artifact_type="FILE"),
        Note(id=str(uuid.uuid4()), engagement_id=eng.id, title=marker, content="n"),
    ])
    await db.flush()
    return eng, {eng.id, f.id, marker}


def _body(r):
    try:
        return r.json()
    except ValueError:
        return r.text


def _comparable(path, r):
    body = _body(r)
    if isinstance(body, dict) and path in IGNORE_KEYS:
        body = {k: v for k, v in body.items() if k not in IGNORE_KEYS[path]}
    return body


async def test_view_all_matches_a_viewer_member_on_every_engagement_read(client, db_session, make_user, authenticate_as):
    from models.permission import VIEW_ALL_ENGAGEMENT_GRANTS

    routes = _routes()
    assert len(routes) > 20, "route discovery found suspiciously few engagement-scoped reads"
    eng, secrets = await _seed(db_session)
    role = await _make_engagement_role(db_session, sorted(VIEW_ALL_ENGAGEMENT_GRANTS))
    member = await make_user()
    await _assign(db_session, member, eng, role)
    viewer = await _view_all_user(db_session, make_user)
    outsider = await make_user()
    await db_session.commit()

    mismatches, leaks, errors = [], [], []
    for kind, path in routes:
        url = _url(kind, path, eng.id)
        got = {}
        for who, user in (("member", member), ("view_all", viewer), ("outsider", outsider)):
            db_session.expunge_all()
            authenticate_as(user)
            got[who] = await client.get(url)
        m, v, o = got["member"], got["view_all"], got["outsider"]
        if m.status_code >= 500 or v.status_code >= 500:
            errors.append(f"{url}: member {m.status_code}, view_all {v.status_code}")
            continue
        if (m.status_code, _comparable(path, m)) != (v.status_code, _comparable(path, v)):
            mismatches.append(f"{url}: member {m.status_code} vs view_all {v.status_code}")
        if o.status_code == 200 and any(s in json.dumps(_body(o)) for s in secrets):
            leaks.append(url)

    assert not errors, "5xx on engagement reads:\n" + "\n".join(errors)
    assert not leaks, "outsider read engagement data from:\n" + "\n".join(leaks)
    assert not mismatches, "view-all differs from a viewer member on:\n" + "\n".join(mismatches)
