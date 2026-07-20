"""End-to-end tests for ``routers/chain_links.py`` — the attack-chain layer.

Drives the real handlers through the httpx ``client`` fixture as an admin
(role bypass on the engagement RBAC gate). Entities are seeded directly on
``db_session``. Covers the validation rules that make the feature correct:

  * POST — finding → testcase happy path → 201; edge readable via the
    for-entity endpoint on both ends (downstream on the source, upstream on
    the target).
  * POST — testcase → testcase is rejected (that's the parent tree), 400.
  * POST — self-loop rejected, 400.
  * POST — cross-engagement endpoint rejected, 400.
  * POST — duplicate and inverse both 409.
  * DELETE of the source finding sweeps the chain edge (orphan cleanup).
"""

from __future__ import annotations

import uuid

import pytest

from sqlalchemy import select

from models.engagement import Engagement
from models.finding import Finding, Severity, FindingStatus
from models.testcase import TestCase
from models.vault import VaultItem
from models.chain_link import ChainLink
from models.associations import FindingTestCase


async def _make_engagement(db, name="Chain Eng") -> Engagement:
    eng = Engagement(
        id=str(uuid.uuid4()), name=name, client_name="ACME Corp",
        engagement_type="external_pentest",
    )
    db.add(eng)
    await db.flush()
    return eng


async def _make_finding(db, engagement_id, title="SQLi") -> Finding:
    f = Finding(
        id=str(uuid.uuid4()), engagement_id=engagement_id, title=title,
        description="d", severity=Severity.HIGH, status=FindingStatus.OPEN,
    )
    db.add(f)
    await db.flush()
    return f


async def _make_testcase(db, engagement_id, title="Exploit") -> TestCase:
    tc = TestCase(
        id=str(uuid.uuid4()), engagement_id=engagement_id, title=title,
        category="web", description="d",
    )
    db.add(tc)
    await db.flush()
    return tc


async def _make_vault(db, engagement_id, name="DC creds") -> VaultItem:
    v = VaultItem(
        id=str(uuid.uuid4()), engagement_id=engagement_id, name=name,
        item_type="CREDENTIAL",
    )
    db.add(v)
    await db.flush()
    return v


@pytest.mark.asyncio
async def test_create_and_read_chain_edge(client, db_session, make_user, authenticate_as):
    admin = await make_user(role="admin")
    authenticate_as(admin)
    eng = await _make_engagement(db_session)
    finding = await _make_finding(db_session, eng.id)
    tc = await _make_testcase(db_session, eng.id)

    # finding led to testcase
    resp = await client.post(f"/engagements/{eng.id}/chain-links", json={
        "source_type": "finding", "source_id": finding.id,
        "target_type": "testcase", "target_id": tc.id,
        "note": "SQLi gave a shell; ran post-exploit enum",
    })
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["source"]["label"] == "SQLi"
    assert body["target"]["label"] == "Exploit"
    assert body["note"].startswith("SQLi gave")

    # From the finding's view, the testcase is downstream (an effect).
    r_src = await client.get(f"/engagements/{eng.id}/chain-links/for/finding/{finding.id}")
    assert r_src.status_code == 200
    d = r_src.json()
    assert len(d["downstream"]) == 1 and d["downstream"][0]["node"]["id"] == tc.id
    assert d["upstream"] == []

    # From the testcase's view, the finding is upstream (a cause).
    r_tgt = await client.get(f"/engagements/{eng.id}/chain-links/for/testcase/{tc.id}")
    u = r_tgt.json()
    assert len(u["upstream"]) == 1 and u["upstream"][0]["node"]["id"] == finding.id
    assert u["downstream"] == []


@pytest.mark.asyncio
async def test_testcase_to_testcase_rejected(client, db_session, make_user, authenticate_as):
    admin = await make_user(role="admin")
    authenticate_as(admin)
    eng = await _make_engagement(db_session)
    tc1 = await _make_testcase(db_session, eng.id, "TC1")
    tc2 = await _make_testcase(db_session, eng.id, "TC2")

    resp = await client.post(f"/engagements/{eng.id}/chain-links", json={
        "source_type": "testcase", "source_id": tc1.id,
        "target_type": "testcase", "target_id": tc2.id,
    })
    assert resp.status_code == 400
    assert "tree" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_self_loop_rejected(client, db_session, make_user, authenticate_as):
    admin = await make_user(role="admin")
    authenticate_as(admin)
    eng = await _make_engagement(db_session)
    f = await _make_finding(db_session, eng.id)

    resp = await client.post(f"/engagements/{eng.id}/chain-links", json={
        "source_type": "finding", "source_id": f.id,
        "target_type": "finding", "target_id": f.id,
    })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_cross_engagement_rejected(client, db_session, make_user, authenticate_as):
    admin = await make_user(role="admin")
    authenticate_as(admin)
    eng_a = await _make_engagement(db_session, "A")
    eng_b = await _make_engagement(db_session, "B")
    f_a = await _make_finding(db_session, eng_a.id)
    v_b = await _make_vault(db_session, eng_b.id)  # foreign endpoint

    resp = await client.post(f"/engagements/{eng_a.id}/chain-links", json={
        "source_type": "finding", "source_id": f_a.id,
        "target_type": "vault_item", "target_id": v_b.id,
    })
    assert resp.status_code == 400
    assert "different engagement" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_duplicate_and_inverse_conflict(client, db_session, make_user, authenticate_as):
    admin = await make_user(role="admin")
    authenticate_as(admin)
    eng = await _make_engagement(db_session)
    f = await _make_finding(db_session, eng.id)
    v = await _make_vault(db_session, eng.id)

    base = {
        "source_type": "finding", "source_id": f.id,
        "target_type": "vault_item", "target_id": v.id,
    }
    assert (await client.post(f"/engagements/{eng.id}/chain-links", json=base)).status_code == 201
    # exact duplicate
    assert (await client.post(f"/engagements/{eng.id}/chain-links", json=base)).status_code == 409
    # inverse (would form a 2-cycle)
    inverse = {
        "source_type": "vault_item", "source_id": v.id,
        "target_type": "finding", "target_id": f.id,
    }
    assert (await client.post(f"/engagements/{eng.id}/chain-links", json=inverse)).status_code == 409


@pytest.mark.asyncio
async def test_flat_link_surfaces_as_candidate_then_promotes(client, db_session, make_user, authenticate_as):
    admin = await make_user(role="admin")
    authenticate_as(admin)
    eng = await _make_engagement(db_session)
    finding = await _make_finding(db_session, eng.id)
    tc = await _make_testcase(db_session, eng.id)

    # Flat-link the finding and testcase (the existing "Link" association),
    # but no chain edge yet.
    db_session.add(FindingTestCase(finding_id=finding.id, testcase_id=tc.id))
    await db_session.flush()

    # The testcase should show up as a promotable candidate on the finding.
    r = await client.get(f"/engagements/{eng.id}/chain-links/for/finding/{finding.id}")
    body = r.json()
    assert body["upstream"] == [] and body["downstream"] == []
    assert [c["id"] for c in body["candidates"]] == [tc.id]

    # Promote it as an effect (finding → testcase).
    assert (await client.post(f"/engagements/{eng.id}/chain-links", json={
        "source_type": "finding", "source_id": finding.id,
        "target_type": "testcase", "target_id": tc.id,
    })).status_code == 201

    # Now it's chained (downstream) and no longer a candidate.
    r2 = (await client.get(f"/engagements/{eng.id}/chain-links/for/finding/{finding.id}")).json()
    assert [n["node"]["id"] for n in r2["downstream"]] == [tc.id]
    assert r2["candidates"] == []


@pytest.mark.asyncio
async def test_for_entity_rejects_foreign_entity(client, db_session, make_user, authenticate_as):
    """The for-entity endpoint must not leak another engagement's flat-linked
    items as candidates (the entity has to belong to the URL engagement)."""
    admin = await make_user(role="admin")
    authenticate_as(admin)
    eng_a = await _make_engagement(db_session, "A")
    eng_b = await _make_engagement(db_session, "B")
    f_b = await _make_finding(db_session, eng_b.id)
    tc_b = await _make_testcase(db_session, eng_b.id)
    db_session.add(FindingTestCase(finding_id=f_b.id, testcase_id=tc_b.id))
    await db_session.flush()

    # Ask engagement A about engagement B's finding → must 404, not leak tc_b.
    r = await client.get(f"/engagements/{eng_a.id}/chain-links/for/finding/{f_b.id}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_graph_dedup_is_direction_aware(client, db_session, make_user):
    """The grey 'discovered' edge (testcase→finding) is suppressed only when a
    chain edge runs the SAME direction; an opposite-direction chain leaves it."""
    from routers.attack_graph import get_attack_graph
    admin = await make_user(role="admin")
    eng = await _make_engagement(db_session)
    f = await _make_finding(db_session, eng.id)
    tc = await _make_testcase(db_session, eng.id)
    db_session.add(FindingTestCase(finding_id=f.id, testcase_id=tc.id))
    await db_session.flush()

    src, tgt = f"testcase-{tc.id}", f"finding-{f.id}"

    def n_discovered(g):
        return sum(1 for e in g["edges"]
                   if e.get("label") == "discovered" and e["source"] == src and e["target"] == tgt)

    # No chain yet → the discovered edge is present.
    assert n_discovered(await get_attack_graph(eng.id, db_session, admin)) == 1

    # Opposite-direction chain (finding → testcase) does NOT suppress it.
    op = ChainLink(id=str(uuid.uuid4()), engagement_id=eng.id,
                   source_type="finding", source_id=f.id,
                   target_type="testcase", target_id=tc.id, relation="led_to")
    db_session.add(op)
    await db_session.flush()
    assert n_discovered(await get_attack_graph(eng.id, db_session, admin)) == 1

    # Same-direction chain (testcase → finding) DOES suppress it.
    await db_session.delete(op)
    await db_session.flush()
    same = ChainLink(id=str(uuid.uuid4()), engagement_id=eng.id,
                     source_type="testcase", source_id=tc.id,
                     target_type="finding", target_id=f.id, relation="led_to")
    db_session.add(same)
    await db_session.flush()
    assert n_discovered(await get_attack_graph(eng.id, db_session, admin)) == 0


@pytest.mark.asyncio
async def test_delete_finding_sweeps_chain(client, db_session, make_user, authenticate_as):
    admin = await make_user(role="admin")
    authenticate_as(admin)
    eng = await _make_engagement(db_session)
    f = await _make_finding(db_session, eng.id)
    tc = await _make_testcase(db_session, eng.id)

    assert (await client.post(f"/engagements/{eng.id}/chain-links", json={
        "source_type": "finding", "source_id": f.id,
        "target_type": "testcase", "target_id": tc.id,
    })).status_code == 201

    # The edge exists.
    n_before = len((await db_session.execute(
        select(ChainLink).where(ChainLink.engagement_id == eng.id)
    )).scalars().all())
    assert n_before == 1

    # Delete the source finding → its chain edges must be swept.
    resp = await client.delete(f"/findings/{f.id}")
    assert resp.status_code == 204, resp.text

    n_after = len((await db_session.execute(
        select(ChainLink).where(ChainLink.engagement_id == eng.id)
    )).scalars().all())
    assert n_after == 0
