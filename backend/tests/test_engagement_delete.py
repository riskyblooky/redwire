"""Deleting an engagement removes (or detaches) everything that belongs to it.

Seeds one of each common child record — finding, asset, test case, evidence,
note, thread + comment, vault item, chain link, cleanup artifact, spray
campaign + result, assignment, activity — deletes the engagement through the
API, then walks *every* foreign key that points at engagements.id and
asserts no row still references the deleted id. New tables are covered
automatically: one whose FK has no ON DELETE rule makes the delete fail, and
one whose rows linger fails the sweep.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text

from models.asset import Asset
from models.chain_link import ChainLink
from models.cleanup_artifact import CleanupArtifact
from models.discussion import ActivityLog, Comment, Thread
from models.engagement import Engagement
from models.evidence import Evidence
from models.note import Note
from models.spray import SprayCampaign, SprayResult
from models.testcase import TestCase as TestCaseModel
from models.vault import VaultItem
from tests.test_authz_boundaries import _assign, _make_engagement, _make_engagement_role, _make_finding


@pytest.fixture
def deleted_keys(monkeypatch):
    import utils.storage_cleanup as sc
    keys: list[str] = []

    async def fake_delete(k):
        keys.extend(k)
        return len(k)
    monkeypatch.setattr(sc, "delete_objects", fake_delete)
    return keys


def _new_id() -> str:
    return str(uuid.uuid4())


async def test_engagement_delete_leaves_nothing_behind(client, db_session, make_user, authenticate_as, deleted_keys):
    from database import Base
    admin = await make_user(role="admin")
    member = await make_user()
    eng = await _make_engagement(db_session)
    finding = await _make_finding(db_session, eng)
    asset = Asset(id=_new_id(), engagement_id=eng.id, name="web01", asset_type="Server", identifier="10.0.0.5")
    tc = TestCaseModel(id=_new_id(), engagement_id=eng.id, title="t", category="web", description="d")
    note = Note(id=_new_id(), engagement_id=eng.id, title="n", content="c")
    vault = VaultItem(id=_new_id(), engagement_id=eng.id, name="creds", item_type="CREDENTIAL")
    cleanup = CleanupArtifact(id=_new_id(), engagement_id=eng.id, title="dropped shell", artifact_type="file")
    campaign = SprayCampaign(id=_new_id(), engagement_id=eng.id, name="spray")
    thread = Thread(id=_new_id(), engagement_id=eng.id, resource_type="finding", resource_id=finding.id, title="t")
    db_session.add_all([asset, tc, note, vault, cleanup, campaign, thread])
    await db_session.flush()
    evidence = Evidence(id=_new_id(), finding_id=finding.id, engagement_id=eng.id, filename="k1.png",
                        original_filename="a.png", file_path="k1.png", file_size=1, mime_type="image/png")
    comment = Comment(id=_new_id(), thread_id=thread.id, content="hi")
    result = SprayResult(id=_new_id(), campaign_id=campaign.id, username="bob", result="failed")
    chain = ChainLink(id=_new_id(), engagement_id=eng.id, source_type="finding", source_id=finding.id,
                      target_type="testcase", target_id=tc.id)
    log = ActivityLog(engagement_id=eng.id, user_id=member.id, action="created_finding",
                      resource_type="finding", resource_id=finding.id)
    db_session.add_all([evidence, comment, result, chain, log])
    await db_session.flush()
    await _assign(db_session, member, eng, await _make_engagement_role(db_session, ["engagement_view"]))

    authenticate_as(admin)
    r = await client.delete(f"/engagements/{eng.id}")
    assert r.status_code == 204, r.text

    assert (await db_session.execute(select(Engagement).where(Engagement.id == eng.id))).first() is None
    # Grandchildren that hang off a child, not the engagement itself.
    for model, row_id in ((Comment, comment.id), (SprayResult, result.id), (Evidence, evidence.id)):
        assert (await db_session.execute(select(model.id).where(model.id == row_id))).first() is None, model.__name__

    # Every FK to engagements.id: nothing may still point at the deleted id.
    leftovers = []
    for table in Base.metadata.sorted_tables:
        for fk in table.foreign_keys:
            if fk.column.table.name == "engagements" and fk.column.name == "id":
                col = fk.parent.name
                n = (await db_session.execute(
                    text(f'SELECT count(*) FROM "{table.name}" WHERE "{col}" = :e'), {"e": eng.id})).scalar()
                if n:
                    leftovers.append(f"{table.name}.{col}: {n}")
    assert not leftovers, leftovers

    # The evidence object is queued for storage cleanup.
    assert "k1.png" in deleted_keys
