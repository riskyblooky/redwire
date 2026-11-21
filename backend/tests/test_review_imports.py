"""Review sweep: imports, parsers, vault."""

from __future__ import annotations

import uuid

import pytest

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


async def test_port_filter_does_not_multiply_the_thread_count(client, db_session, make_user, authenticate_as):
    from models.asset import Asset
    from models.asset_port import AssetPort
    from models.discussion import Thread
    admin = await make_user(role="admin")
    eng = await _make_engagement(db_session)
    host = Asset(id=str(uuid.uuid4()), engagement_id=eng.id, name="web", asset_type="Server",
                 identifier="10.6.6.6", created_by=admin.id)
    db_session.add(host)
    await db_session.flush()
    for n in (80, 443, 8080):
        db_session.add(AssetPort(id=str(uuid.uuid4()), asset_id=host.id, port_number=n, protocol="TCP",
                                 state="OPEN", service_name="http"))
    db_session.add(Thread(id=str(uuid.uuid4()), engagement_id=eng.id, resource_type="asset",
                          resource_id=host.id, title="t", created_by=admin.id))
    await db_session.flush()
    authenticate_as(admin)

    r = await client.get("/assets", params={"engagement_id": eng.id, "service": "http"})

    assert r.status_code == 200, r.text
    body = r.json()
    rows = body["items"] if isinstance(body, dict) else body
    [row] = [a for a in rows if a["id"] == host.id]
    assert row["unresolved_thread_count"] == 1


@pytest.mark.parametrize("sort_by", ["unresolved_thread_count", "created_by_username"])
async def test_asset_list_sorts_by_discussions_and_creator(sort_by, client, db_session, make_user,
                                                           authenticate_as):
    from datetime import datetime
    from models.asset import Asset
    from models.discussion import Thread
    admin = await make_user(role="admin", username=f"aaa_{uuid.uuid4().hex[:6]}")
    zed = await make_user(username=f"zzz_{uuid.uuid4().hex[:6]}")
    eng = await _make_engagement(db_session)
    # "quiet" is the newer asset, so created_at order would put it first.
    busy = Asset(id=str(uuid.uuid4()), engagement_id=eng.id, name="busy", asset_type="Server",
                 identifier="10.5.5.1", created_by=zed.id, created_at=datetime(2026, 1, 1))
    quiet = Asset(id=str(uuid.uuid4()), engagement_id=eng.id, name="quiet", asset_type="Server",
                  identifier="10.5.5.2", created_by=admin.id, created_at=datetime(2026, 2, 1))
    db_session.add_all([busy, quiet])
    await db_session.flush()
    db_session.add_all([Thread(id=str(uuid.uuid4()), engagement_id=eng.id, resource_type="asset",
                               resource_id=busy.id, title=f"t{i}", created_by=admin.id) for i in range(2)])
    await db_session.flush()
    authenticate_as(admin)

    r = await client.get("/assets", params={"engagement_id": eng.id, "sort_by": sort_by, "sort_order": "desc"})

    assert r.status_code == 200, r.text
    body = r.json()
    rows = body["items"] if isinstance(body, dict) else body
    assert [a["name"] for a in rows] == ["busy", "quiet"]


SPRAY_LOG = """\
SMB   10.0.0.5   445  DC01   [*] Windows Server 2019 (name:DC01) (domain:lab.local)
SMB   10.0.0.5   445  DC01   [-] lab.local\\alice:Summer2025! STATUS_LOGON_FAILURE
SMB   10.0.0.5   445  DC01   [+] lab.local\\bob:Winter 2025 (Pwn3d!)
SMB   10.0.0.5   445  DC01   [+] lab.local\\guest:
SMB   10.0.0.5   445  DC01   [-] Domain: lab.local
SMB   10.0.0.5   445  DC01   [+] Error: could not enumerate shares
SSH   dc02.lab.local 22  dc02  [+] pi:raspberry  Linux - Shell access!
SSH   fe80::1    22  fe80::1 [-] pi:wrong
"""


def test_spray_parser_keeps_real_credentials_only():
    from utils.parsers.netexec import parse_netexec_log
    got = {(r.target_host, r.username, r.password, r.result) for r in parse_netexec_log(SPRAY_LOG).results}
    assert got == {
        ("10.0.0.5", "alice", "Summer2025!", "failed"),
        ("10.0.0.5", "bob", "Winter 2025", "success_admin"),
        ("10.0.0.5", "guest", "", "success"),
        ("dc02.lab.local", "pi", "raspberry", "success"),
        ("fe80::1", "pi", "wrong", "failed"),
    }
