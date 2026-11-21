"""Finding cross-link endpoints follow the owner-vs-ANY rule: with
finding_edit alone you can change the links of your own findings only."""

from __future__ import annotations

import uuid

import pytest

from tests.test_authz_boundaries import _assign, _make_engagement, _make_engagement_role, _make_finding


@pytest.mark.parametrize("kind", ["testcases", "vault-items", "cleanup-artifacts"])
async def test_finding_edit_alone_cannot_relink_someone_elses_finding(kind, client, db_session, make_user,
                                                                      authenticate_as):
    from models.cleanup_artifact import CleanupArtifact
    from models.testcase import TestCase
    from models.vault import VaultItem
    author, other = await make_user(), await make_user()
    eng = await _make_engagement(db_session)
    role = await _make_engagement_role(db_session, ["engagement_view", "finding_view", "finding_edit"])
    await _assign(db_session, other, eng, role)
    theirs = await _make_finding(db_session, eng, created_by=author.id)
    mine = await _make_finding(db_session, eng, created_by=other.id)
    target = {
        "testcases": lambda: TestCase(id=str(uuid.uuid4()), engagement_id=eng.id, title="t", category="Recon",
                                      description="d"),
        "vault-items": lambda: VaultItem(id=str(uuid.uuid4()), engagement_id=eng.id, name="v",
                                         item_type="CREDENTIAL"),
        "cleanup-artifacts": lambda: CleanupArtifact(id=str(uuid.uuid4()), engagement_id=eng.id, title="c",
                                                     artifact_type="FILE"),
    }[kind]()
    db_session.add(target)
    await db_session.flush()
    authenticate_as(other)

    assert (await client.post(f"/findings/{theirs.id}/{kind}/{target.id}")).status_code == 403
    assert (await client.post(f"/findings/{mine.id}/{kind}/{target.id}")).status_code == 204
    assert (await client.delete(f"/findings/{theirs.id}/{kind}/{target.id}")).status_code == 403
