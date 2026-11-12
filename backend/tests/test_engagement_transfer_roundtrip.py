"""Engagement export → import is a round trip: every column of every
transferred table comes back (remapped where it is a reference), unless it
is listed in EXEMPT with the reason."""

from __future__ import annotations

import json
import uuid
from datetime import datetime

from sqlalchemy import select

from models.engagement import Engagement
from models.finding import Finding, Severity, Tag

# Columns that legitimately differ after an import.
EXEMPT = {
    "*": {"id", "engagement_id", "created_by", "updated_by", "created_at", "updated_at"},
    "engagements": {"name"},                # gains " (imported)"
    "attack_graph_layouts": {"positions", "pinned_by", "pinned_at"},  # checked separately
    "vault_items": {"encryption_version", "file_path"},
    "evidence": {"filename", "file_path", "mime_type", "file_size"},
    "finding_assets": {"port_ids"},         # checked separately (remapped)
    "testcase_assets": {"port_ids"},
    "attacker_node_edges": {"target_node_id"},
    "chain_links": {"source_id", "target_id"},
}


def _plain(row, table) -> dict:
    skip = EXEMPT["*"] | EXEMPT.get(table, set())
    out = {}
    for c in row.__table__.columns:
        if c.key in skip or c.foreign_keys:
            continue
        v = getattr(row, c.key)
        out[c.key] = v.value if hasattr(v, "value") else v
    return out


async def _seed(db, users):
    from models.asset import Asset
    from models.asset_port import AssetPort
    from models.testcase import TestCase
    from models.note import Note
    from models.vault import VaultItem
    from models.chain_link import ChainLink
    from models.finding_review import FindingReview
    from models.attacker_node import AttackerNode, AttackerNodeEdge
    from models.attack_graph_layout import AttackGraphLayout
    from models.report_layout import ReportLayout, ReportSection
    from models.engagement_phase import EngagementPhase
    from models.skill import EngagementSkill, Skill, SkillCategory
    from models.associations import (
        EngagementTag, FindingAsset, FindingAttackTechnique, FindingTag, TestCaseAsset,
        TestCaseAttackTechnique, VaultItemAsset,
    )
    author, reviewer = users
    u = lambda: str(uuid.uuid4())  # noqa: E731
    eng = Engagement(
        id=u(), name=f"RT {u()[:8]}", client_name="Acme", engagement_type="Red Team",
        default_classification_level="SECRET", default_classification_suffix="NOFORN",
        ceiling_classification_level="TOP SECRET", custom_fields={"cost_centre": "42"},
        allowed_score_models=["cvss31"], default_score_model="cvss31",
    )
    # The same tag name under two entity types (name-only lookup 500'd).
    ftag = Tag(id=u(), name=f"dup-{u()[:6]}", entity_type="finding", color="#ff0000")
    etag = Tag(id=u(), name=ftag.name, entity_type="engagement", color="#00ff00")
    asset = Asset(id=u(), engagement_id=eng.id, name="dc01", asset_type="Server", identifier="10.0.0.1",
                  custom_fields={"os": "win"})
    port = AssetPort(id=u(), asset_id=asset.id, port_number=445, protocol="TCP", state="OPEN", service_name="smb")
    finding = Finding(
        id=u(), engagement_id=eng.id, title="SMB signing", description="d", severity=Severity.HIGH,
        cvss_score=7.5, cvss_vector="CVSS:3.1/AV:N", score_model="cvss31", score_inputs={"av": "N"},
        classification_level="SECRET", classification_suffix="REL", custom_fields={"ticket": "T-1"},
        created_by=author.id,
    )
    parent = TestCase(id=u(), engagement_id=eng.id, title="parent", category="Recon", description="p",
                      classification_level="CUI", custom_fields={"k": 1})
    child = TestCase(id=u(), engagement_id=eng.id, parent_id=parent.id, title="child", category="Recon",
                     description="c", is_executed=True)
    note_p = Note(id=u(), engagement_id=eng.id, title="parent note", content="x")
    note_c = Note(id=u(), engagement_id=eng.id, parent_id=note_p.id, title="child note", content="y")
    vault = VaultItem(id=u(), engagement_id=eng.id, name="svc", item_type="password", username="svc", password="pw")
    attacker = AttackerNode(id=u(), engagement_id=eng.id, name="APT", point_of_presence="External")
    layout = ReportLayout(id=u(), engagement_id=eng.id, name="Main", is_default=True)
    cat = SkillCategory(id=u(), name=f"cat-{u()[:6]}")
    skill = Skill(id=u(), category_id=cat.id, name="AD")
    db.add_all([eng, ftag, etag, cat])
    await db.flush()
    db.add_all([asset, finding, parent, note_p, vault, attacker, layout, skill])
    await db.flush()
    db.add_all([port, child, note_c])
    await db.flush()
    db.add_all([
        EngagementTag(engagement_id=eng.id, tag_id=etag.id),
        FindingTag(finding_id=finding.id, tag_id=ftag.id),
        FindingAsset(finding_id=finding.id, asset_id=asset.id, port_ids=json.dumps([port.id]),
                     remediated=True, remediated_at=datetime(2026, 1, 2), remediated_by=reviewer.id),
        TestCaseAsset(testcase_id=child.id, asset_id=asset.id, port_ids=json.dumps([port.id])),
        FindingAttackTechnique(finding_id=finding.id, technique_id="T1557.001"),
        TestCaseAttackTechnique(testcase_id=child.id, technique_id="T1046"),
        VaultItemAsset(vault_item_id=vault.id, asset_id=asset.id),
        ChainLink(id=u(), engagement_id=eng.id, source_type="testcase", source_id=child.id,
                  target_type="finding", target_id=finding.id, relation="led_to"),
        FindingReview(id=u(), finding_id=finding.id, reviewer_id=reviewer.id, status="APPROVED"),
        AttackerNodeEdge(id=u(), attacker_node_id=attacker.id, target_node_id=f"testcase-{parent.id}",
                         target_node_type="testcase"),
        AttackGraphLayout(id=u(), engagement_id=eng.id, name="Pinned", is_active=True,
                          positions=json.dumps({f"testcase-{parent.id}": {"x": 1, "y": 2},
                                                f"attacker-{attacker.id}": {"x": 3, "y": 4},
                                                "testcase-not-in-archive": {"x": 0, "y": 0}})),
        ReportSection(id=u(), report_layout_id=layout.id, section_type="text", title="Intro", content="hi",
                      sort_order=1, page_break_before=True, classification_level="SECRET"),
        EngagementPhase(id=u(), engagement_id=eng.id, phase_name="SCOPING", sort_order=1,
                        planned_start=datetime(2026, 2, 1)),
        EngagementSkill(id=u(), engagement_id=eng.id, skill_id=skill.id, min_level=3),
    ])
    await db.flush()
    return eng


async def _rows(db, model, **where):
    q = select(model)
    for k, v in where.items():
        q = q.where(getattr(model, k) == v)
    return (await db.execute(q)).scalars().all()


async def test_export_import_round_trip(client, db_session, make_user, authenticate_as):
    from models.asset import Asset
    from models.asset_port import AssetPort
    from models.testcase import TestCase
    from models.note import Note
    from models.vault import VaultItem
    from models.chain_link import ChainLink
    from models.finding_review import FindingReview
    from models.attacker_node import AttackerNode, AttackerNodeEdge
    from models.attack_graph_layout import AttackGraphLayout
    from models.report_layout import ReportLayout, ReportSection
    from models.engagement_phase import EngagementPhase
    from models.skill import EngagementSkill
    from models.associations import (
        EngagementTag, FindingAsset, FindingAttackTechnique, FindingTag, TestCaseAsset,
        TestCaseAttackTechnique, VaultItemAsset,
    )
    admin = await make_user(role="admin")
    author, reviewer = await make_user(), await make_user()
    old = await _seed(db_session, (author, reviewer))
    old_id = old.id
    db_session.expunge_all()
    authenticate_as(admin)

    exp = await client.get(f"/engagements/{old_id}/export")
    assert exp.status_code == 200, exp.text
    mapping = {reviewer.id: reviewer.id, author.id: author.id}
    imp = await client.post("/engagements/import", data={"user_mapping": json.dumps(mapping)},
                            files={"file": ("e.zip", exp.content, "application/zip")})
    assert imp.status_code == 201, imp.text
    new_id = imp.json()["id"]
    db = db_session

    # Plain columns of every engagement-owned table survive.
    per_engagement = [Engagement, Asset, Finding, TestCase, Note, VaultItem, AttackerNode,
                      ReportLayout, EngagementPhase, EngagementSkill, ChainLink]
    for model in per_engagement:
        key = "id" if model is Engagement else "engagement_id"
        before = sorted((_plain(r, model.__tablename__) for r in await _rows(db, model, **{key: old_id})), key=repr)
        after = sorted((_plain(r, model.__tablename__) for r in await _rows(db, model, **{key: new_id})), key=repr)
        assert after == before, model.__tablename__

    new = lambda model, **w: _rows(db, model, **w)  # noqa: E731
    [nf] = await new(Finding, engagement_id=new_id)
    [na] = await new(Asset, engagement_id=new_id)
    [nport] = await new(AssetPort, asset_id=na.id)
    tcs = {t.title: t for t in await new(TestCase, engagement_id=new_id)}
    notes = {n.title: n for n in await new(Note, engagement_id=new_id)}
    [nv] = await new(VaultItem, engagement_id=new_id)
    [natt] = await new(AttackerNode, engagement_id=new_id)

    # Hierarchies.
    assert tcs["child"].parent_id == tcs["parent"].id
    assert notes["child note"].parent_id == notes["parent note"].id

    # Port links point at the imported port, remediation keeps its author.
    [fa] = await new(FindingAsset, finding_id=nf.id)
    assert json.loads(fa.port_ids) == [nport.id] and fa.asset_id == na.id
    assert fa.remediated and fa.remediated_by == reviewer.id
    [tca] = await new(TestCaseAsset, testcase_id=tcs["child"].id)
    assert json.loads(tca.port_ids) == [nport.id]

    # Tags matched by (name, entity type).
    [ft] = await new(FindingTag, finding_id=nf.id)
    [et] = await new(EngagementTag, engagement_id=new_id)
    tags = {t.id: t.entity_type for t in await _rows(db, Tag)}
    assert tags[ft.tag_id] == "finding" and tags[et.tag_id] == "engagement"

    # ATT&CK, vault-asset, chain links, review.
    assert [r.technique_id for r in await new(FindingAttackTechnique, finding_id=nf.id)] == ["T1557.001"]
    assert [r.technique_id for r in await new(TestCaseAttackTechnique, testcase_id=tcs["child"].id)] == ["T1046"]
    assert [r.asset_id for r in await new(VaultItemAsset, vault_item_id=nv.id)] == [na.id]
    [cl] = await new(ChainLink, engagement_id=new_id)
    assert (cl.source_id, cl.target_id) == (tcs["child"].id, nf.id)
    assert [(r.reviewer_id, r.status) for r in await new(FindingReview, finding_id=nf.id)] == [(reviewer.id, "APPROVED")]

    # Attack graph: edge target and layout keys use the new graph ids.
    [edge] = await new(AttackerNodeEdge, attacker_node_id=natt.id)
    assert edge.target_node_id == f"testcase-{tcs['parent'].id}"
    [lay] = await new(AttackGraphLayout, engagement_id=new_id)
    assert json.loads(lay.positions) == {f"testcase-{tcs['parent'].id}": {"x": 1, "y": 2},
                                         f"attacker-{natt.id}": {"x": 3, "y": 4}}

    # Report section flags.
    [rl] = await new(ReportLayout, engagement_id=new_id)
    [sec] = await new(ReportSection, report_layout_id=rl.id)
    assert sec.page_break_before is True and sec.classification_level == "SECRET"


async def test_unmapped_reviewer_is_not_reattributed_to_importer(client, db_session, make_user, authenticate_as):
    from models.finding_review import FindingReview
    admin = await make_user(role="admin")
    author, reviewer = await make_user(), await make_user()
    old = await _seed(db_session, (author, reviewer))
    old_id = old.id
    db_session.expunge_all()
    authenticate_as(admin)
    exp = await client.get(f"/engagements/{old_id}/export")
    imp = await client.post("/engagements/import", files={"file": ("e.zip", exp.content, "application/zip")})
    assert imp.status_code == 201, imp.text
    [nf] = await _rows(db_session, Finding, engagement_id=imp.json()["id"])
    assert await _rows(db_session, FindingReview, finding_id=nf.id) == []


def test_import_coercion_rejects_wrong_types():
    from routers.engagements_transfer import _plain_fields
    from models.finding import Finding
    parse = lambda v: datetime.fromisoformat(v) if isinstance(v, str) else None  # noqa: E731
    got = _plain_fields(Finding, {
        "title": "t", "cvss_score": "9.8", "severity": "high", "status": "NOPE",
        "score_inputs": "not-a-dict", "custom_fields": {"a": 1}, "engagement_id": "x",
        "created_by": "someone", "id": "x",
    }, parse)
    assert got == {"title": "t", "severity": "HIGH", "custom_fields": {"a": 1}}
