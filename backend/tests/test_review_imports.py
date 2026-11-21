"""Review sweep: imports, parsers, vault."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select

from tests.test_authz_boundaries import _make_engagement
from tests.test_parsers_httpx_nxc import NXC_LOG


async def test_nxc_import_keeps_the_command_line(client, db_session, make_user, authenticate_as):
    """The parser stores the (redacted) command under "command"; the import
    only read "args", nmap's key."""
    from models.scan_import import ScanImport
    admin = await make_user(role="admin")
    eng = await _make_engagement(db_session)
    authenticate_as(admin)

    r = await client.post("/imports/commit", data={"engagement_id": eng.id},
                          files={"file": ("nxc.log", NXC_LOG, "text/plain")})

    assert r.status_code == 200, r.text
    cmd = (await db_session.execute(select(ScanImport.command).where(ScanImport.engagement_id == eng.id))).scalar_one()
    assert cmd and "nxc" in cmd and "Hunter2" not in cmd


async def test_engagement_update_with_null_tag_ids_keeps_tags(client, db_session, make_user, authenticate_as):
    from models.associations import EngagementTag
    from models.finding import Tag
    admin = await make_user(role="admin")
    eng = await _make_engagement(db_session)
    tag = Tag(id=str(uuid.uuid4()), name=f"t-{uuid.uuid4().hex[:6]}", color="#ff0000", entity_type="engagement")
    db_session.add(tag)
    await db_session.flush()
    db_session.add(EngagementTag(engagement_id=eng.id, tag_id=tag.id))
    await db_session.flush()
    authenticate_as(admin)

    r = await client.put(f"/engagements/{eng.id}", json={"description": "x", "tag_ids": None})

    assert r.status_code == 200, r.text
    tags = (await db_session.execute(select(EngagementTag.tag_id).where(EngagementTag.engagement_id == eng.id)
                                     .execution_options(populate_existing=True))).scalars().all()
    assert tags == [tag.id]


async def test_vault_items_cannot_be_retyped_to_or_from_file(client, db_session, make_user, authenticate_as):
    from models.vault import VaultItem
    admin = await make_user(role="admin")
    eng = await _make_engagement(db_session)
    file_item = VaultItem(id=str(uuid.uuid4()), engagement_id=eng.id, name="f", item_type="FILE", created_by=admin.id)
    cred = VaultItem(id=str(uuid.uuid4()), engagement_id=eng.id, name="c", item_type="CREDENTIAL", created_by=admin.id)
    db_session.add_all([file_item, cred])
    await db_session.flush()
    authenticate_as(admin)

    assert (await client.patch(f"/vault/{file_item.id}", json={"item_type": "CREDENTIAL"})).status_code == 400
    assert (await client.patch(f"/vault/{cred.id}", json={"item_type": "FILE"})).status_code == 400


def _nuclei(*hosts):
    import json
    return "".join(json.dumps({"template-id": "t1", "info": {"name": "Exposed Panel", "severity": "high"},
                               "host": f"http://{h}:8080", "matched-at": f"http://{h}:8080/admin",
                               "ip": h, "type": "http"}) + "\n" for h in hosts).encode()


async def test_reimport_links_a_known_finding_to_new_hosts(client, db_session, make_user, authenticate_as):
    from models.asset import Asset
    from models.finding import Finding
    from models.associations import FindingAsset
    admin = await make_user(role="admin")
    eng = await _make_engagement(db_session)
    authenticate_as(admin)
    post = lambda body: client.post("/imports/commit", data={"engagement_id": eng.id},
                                    files={"file": ("n.jsonl", body, "application/json")})

    assert (await post(_nuclei("10.7.7.1"))).status_code == 200
    r = await post(_nuclei("10.7.7.1", "10.7.7.2"))
    assert r.status_code == 200, r.text

    linked = (await db_session.execute(
        select(Asset.identifier).join(FindingAsset, FindingAsset.asset_id == Asset.id)
        .join(Finding, Finding.id == FindingAsset.finding_id).where(Finding.engagement_id == eng.id)
    )).scalars().all()
    assert sorted(linked) == ["10.7.7.1", "10.7.7.2"]
    assert (await db_session.execute(select(func.count()).select_from(Finding)
                                     .where(Finding.engagement_id == eng.id))).scalar() == 1


async def test_reimport_updates_a_known_port_and_marks_the_asset_scanned(client, db_session, make_user,
                                                                         authenticate_as):
    from models.asset import Asset
    from models.asset_port import AssetPort
    admin = await make_user(role="admin")
    eng = await _make_engagement(db_session)
    host = Asset(id=str(uuid.uuid4()), engagement_id=eng.id, name="h", asset_type="Server",
                 identifier="10.8.8.8", is_scanned=False, created_by=admin.id)
    db_session.add(host)
    await db_session.flush()
    db_session.add(AssetPort(id=str(uuid.uuid4()), asset_id=host.id, port_number=22, protocol="TCP",
                             state="OPEN", service_name="ssh", version="OpenSSH 7.4"))
    await db_session.flush()
    authenticate_as(admin)
    nmap = b"""<?xml version="1.0"?><nmaprun scanner="nmap" args="nmap -sV 10.8.8.8">
      <host><status state="up"/><address addr="10.8.8.8" addrtype="ipv4"/><ports>
        <port protocol="tcp" portid="22"><state state="closed"/><service name="ssh" product="OpenSSH" version="9.6"/></port>
      </ports></host></nmaprun>"""

    r = await client.post("/imports/commit", data={"engagement_id": eng.id},
                          files={"file": ("scan.xml", nmap, "application/xml")})

    assert r.status_code == 200, r.text
    port = (await db_session.execute(select(AssetPort).where(AssetPort.asset_id == host.id)
                                     .execution_options(populate_existing=True))).scalar_one()
    assert port.state.value == "CLOSED" and "9.6" in (port.version or "")
    scanned = (await db_session.execute(select(Asset.is_scanned).where(Asset.id == host.id)
                                        .execution_options(populate_existing=True))).scalar_one()
    assert scanned is True
