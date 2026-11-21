"""GHSA-7x2f-ff7r-h388 — deferred items #8 and #14.

#8  (CWE-20)   Thread.resource_type + ActivityLog.resource_type on
    engagement import are coerced against the ResourceType values.
    Unknown values fall back to ENGAGEMENT instead of being stored.

#14 (CWE-696)  Runbook apply commits the created test cases before the
    activity-log side effect, which is wrapped so a log failure can't
    roll back the applied test cases.
"""

from __future__ import annotations

import io
import json
import uuid
import zipfile

from sqlalchemy import select

from tests.test_authz_boundaries import _make_engagement


# ── #8: unknown resource_type on import ──────────────────────────────


def _retarget(archive: bytes, mutate) -> bytes:
    """Apply ``mutate`` to the archive's data JSON and re-sign the manifest
    the way the export does, so the import's integrity check passes."""
    from routers.engagements_transfer import _compute_root_digest, _sha256_hex

    src = zipfile.ZipFile(io.BytesIO(archive))
    members = {n: src.read(n) for n in src.namelist() if n != "manifest.json"}
    manifest = json.loads(src.read("manifest.json"))
    [name] = [n for n, b in members.items() if n.endswith(".json") and b'"threads"' in b]
    data = json.loads(members[name])
    mutate(data)
    members[name] = json.dumps(data).encode()
    manifest["digests"] = {n: _sha256_hex(members[n]) for n in sorted(members)}
    manifest["root_digest"] = _compute_root_digest(manifest["digests"])
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
        for n in sorted(members):
            zf.writestr(n, members[n])
    return out.getvalue()


async def test_import_coerces_unknown_resource_types(client, db_session, make_user, authenticate_as):
    from models.discussion import ActivityLog, Thread

    admin = await make_user(role="admin")
    eng = await _make_engagement(db_session)
    db_session.add(Thread(id=str(uuid.uuid4()), engagement_id=eng.id, resource_type="finding",
                          title="t", created_by=admin.id))
    db_session.add(ActivityLog(id=str(uuid.uuid4()), engagement_id=eng.id, user_id=admin.id,
                               action="x", resource_type="finding", resource_id="r"))
    await db_session.flush()
    authenticate_as(admin)

    exp = await client.get(f"/engagements/{eng.id}/export")
    assert exp.status_code == 200, exp.text

    def poison(data):
        assert data["threads"] and data["activity_logs"]
        for row in data["threads"] + data["activity_logs"]:
            row["resource_type"] = "<script>"
    imp = await client.post("/engagements/import",
                            files={"file": ("e.zip", _retarget(exp.content, poison), "application/zip")})
    assert imp.status_code == 201, imp.text
    new_id = imp.json()["id"]

    threads = (await db_session.execute(select(Thread.resource_type).where(Thread.engagement_id == new_id))).scalars().all()
    logs = (await db_session.execute(
        select(ActivityLog.resource_type).where(ActivityLog.engagement_id == new_id, ActivityLog.action == "x")
    )).scalars().all()
    assert threads == ["engagement"]
    assert logs == ["engagement"]


# ── #14: runbook apply survives an activity-log failure ──────────────


async def test_runbook_apply_keeps_testcases_when_logging_fails(client, db_session, make_user, authenticate_as, monkeypatch):
    from models.template_status import TemplateStatus
    from models.testcase import TestCase
    from models.testcase_template import TestCaseTemplate
    from utils import collaboration

    admin = await make_user(role="admin")
    authenticate_as(admin)
    tmpl = TestCaseTemplate(id=str(uuid.uuid4()), title="Kerberoast", category="Exploitation",
                            description="body", status=TemplateStatus.PUBLISHED, created_by=admin.id)
    db_session.add(tmpl)
    await db_session.flush()
    rb = await client.post("/runbooks", json={"name": "AD", "items": [
        {"temp_key": "a", "template_id": tmpl.id, "sort_order": 0}]})
    assert rb.status_code == 201, rb.text
    eng = await _make_engagement(db_session)

    calls = []

    async def _log_fails(*a, **k):
        calls.append(k.get("action"))
        raise RuntimeError("activity log down")
    monkeypatch.setattr(collaboration, "create_activity_log", _log_fails)

    r = await client.post(f"/runbooks/{rb.json()['id']}/apply/{eng.id}")

    assert r.status_code == 201, r.text
    titles = (await db_session.execute(select(TestCase.title).where(TestCase.engagement_id == eng.id))).scalars().all()
    assert titles == ["Kerberoast"]
    assert calls, "the apply path never reached the activity log"
