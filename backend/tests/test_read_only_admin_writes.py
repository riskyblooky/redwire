"""READ_ONLY_ADMIN sees everything but writes nothing without an explicit
grant. Pins the write gates that still let the role through by listing it
next to ADMIN / TEAM_LEAD (the follow-up sweep to GHSA-rq7c issue 1): report
layouts, scan imports, the link/unlink helpers, cleanup-artifact edits and
infra-vault management."""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from models.asset import Asset
from models.cleanup_artifact import CleanupArtifact
from models.engagement import Engagement
from models.finding import Finding
from models.infra_item import InfraItem
from models.note import Note
from models.report_layout import ReportLayout
from models.testcase import TestCase


@pytest.fixture
async def world(db_session, make_user):
    ro = await make_user(role="read_only_admin", username=f"ro_{uuid.uuid4().hex[:6]}")
    admin = await make_user(role="admin", username=f"ad_{uuid.uuid4().hex[:6]}")
    eng = Engagement(id=str(uuid.uuid4()), name="RO", client_name="ACME",
                     engagement_type="external_pentest", created_by=admin.id)
    db_session.add(eng)
    await db_session.flush()
    rows = dict(
        asset=Asset(id=str(uuid.uuid4()), engagement_id=eng.id, name="a", asset_type="Server",
                    identifier="10.0.0.1", created_by=admin.id),
        finding=Finding(id=str(uuid.uuid4()), engagement_id=eng.id, title="F", description="d", severity="LOW",
                        created_by=admin.id),
        testcase=TestCase(id=str(uuid.uuid4()), engagement_id=eng.id, title="T", category="Recon", description="d", created_by=admin.id),
        note=Note(id=str(uuid.uuid4()), engagement_id=eng.id, title="N", created_by=admin.id),
        artifact=CleanupArtifact(id=str(uuid.uuid4()), engagement_id=eng.id, title="C",
                                 artifact_type="file", created_by=admin.id),
        infra=InfraItem(id=str(uuid.uuid4()), name="redirector", created_by=admin.id),
        layout=ReportLayout(id=str(uuid.uuid4()), engagement_id=eng.id, name="L"),
    )
    db_session.add_all(rows.values())
    await db_session.flush()
    return dict(ro=ro, admin=admin, eng=eng, **rows)


def _gates(w, db):
    from routers import assets, cleanup_artifacts, findings, imports, infra, notes, report_layouts, testcases
    return {
        "report_layout_write": lambda u: report_layouts._check_report_write(u, w["eng"].id, db),
        "scan_import": lambda u: imports._check_import_permission(u, w["eng"].id, db),
        "asset_link": lambda u: assets._require_asset(w["asset"].id, db, u),
        "finding_link": lambda u: findings._require_finding(w["finding"].id, db, u),
        "testcase_link": lambda u: testcases._require_testcase(w["testcase"].id, db, u),
        "note_link": lambda u: notes._get_note_with_perm_check(w["note"].id, db, u),
        "cleanup_edit": lambda u: cleanup_artifacts._require_artifact_edit(w["artifact"], u, db),
        "infra_vault_manage": lambda u: infra._check_vault_access(w["infra"].id, u, db, require_manage=True),
    }


GATES = ["report_layout_write", "scan_import", "asset_link", "finding_link", "testcase_link",
         "note_link", "cleanup_edit", "infra_vault_manage"]


@pytest.mark.parametrize("gate", GATES)
async def test_read_only_admin_refused(world, db_session, gate):
    with pytest.raises(HTTPException) as exc:
        await _gates(world, db_session)[gate](world["ro"])
    assert exc.value.status_code == 403


@pytest.mark.parametrize("gate", GATES)
async def test_admin_still_allowed(world, db_session, gate):
    await _gates(world, db_session)[gate](world["admin"])


async def test_read_only_admin_keeps_infra_vault_view(world, db_session):
    from routers import infra
    await infra._check_vault_access(world["infra"].id, world["ro"], db_session)


async def test_report_layout_save_refused_but_readable(client, world, authenticate_as):
    authenticate_as(world["ro"])
    eng, layout = world["eng"].id, world["layout"].id
    assert (await client.get(f"/engagements/{eng}/report-layouts")).status_code == 200
    r = await client.put(f"/engagements/{eng}/report-layouts/{layout}", json={"name": "hijacked", "sections": []})
    assert r.status_code == 403
