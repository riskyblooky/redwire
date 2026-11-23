"""One asset per identifier per engagement, ignoring case and surrounding
spaces: create and rename refuse a duplicate, spray matches the existing
asset whatever the case, and an imported bundle that holds two rows for one
host folds them (links and ports follow)."""

from __future__ import annotations

import io
import json
import uuid
import zipfile

from sqlalchemy import func, select

from models.asset import Asset
from models.engagement import Engagement


async def _engagement(db, owner):
    eng = Engagement(id=str(uuid.uuid4()), name=f"E-{uuid.uuid4().hex[:6]}", client_name="ACME",
                     engagement_type="external_pentest", created_by=owner.id)
    db.add(eng)
    await db.flush()
    return eng


def _asset(eng, ident, **kw):
    return {"engagement_id": eng.id, "name": kw.pop("name", ident), "asset_type": "Server", "identifier": ident, **kw}


async def test_create_and_rename_refuse_a_duplicate_identifier(client, db_session, make_user, authenticate_as):
    admin = await make_user(role="admin")
    authenticate_as(admin)
    eng = await _engagement(db_session, admin)
    r = await client.post("/assets", json=_asset(eng, " Host01.corp "))
    assert r.status_code == 201, r.text
    assert r.json()["identifier"] == "Host01.corp"  # stored trimmed

    dup = await client.post("/assets", json=_asset(eng, "host01.CORP"))
    assert dup.status_code == 409 and "Host01.corp" in dup.json()["detail"]

    other = await client.post("/assets", json=_asset(eng, "host02.corp"))
    assert other.status_code == 201
    ren = await client.put(f"/assets/{other.json()['id']}", json={"identifier": "HOST01.corp"})
    assert ren.status_code == 409
    same = await client.put(f"/assets/{r.json()['id']}", json={"identifier": "host01.corp"})  # itself: fine
    assert same.status_code == 200, same.text


async def test_spray_links_to_the_existing_asset_case_insensitively(client, db_session, make_user, authenticate_as):
    admin = await make_user(role="admin")
    authenticate_as(admin)
    eng = await _engagement(db_session, admin)
    assert (await client.post("/assets", json=_asset(eng, "dc01.corp"))).status_code == 201
    r = await client.post("/spray/commit", json={
        "engagement_id": eng.id, "name": "s", "create_missing_assets": True,
        "results": [{"username": "a", "result": "failed", "target_host": "DC01.corp"},
                    {"username": "b", "result": "failed", "target_host": "new01"},
                    {"username": "c", "result": "failed", "target_host": "NEW01"}],
    })
    assert r.status_code == 201, r.text
    idents = sorted(i.lower() for i in (await db_session.execute(
        select(Asset.identifier).where(Asset.engagement_id == eng.id))).scalars())
    assert idents == ["dc01.corp", "new01"]  # DC01 matched dc01; new01/NEW01 made one


async def test_import_folds_duplicate_assets_in_a_bundle(client, db_session, make_user, authenticate_as):
    from models.asset_port import AssetPort
    from models.associations import FindingAsset
    from models.finding import Finding
    admin = await make_user(role="admin")
    authenticate_as(admin)
    eng = await _engagement(db_session, admin)
    a = Asset(id=str(uuid.uuid4()), engagement_id=eng.id, name="web", asset_type="Server", identifier="web01", created_by=admin.id)
    f = Finding(id=str(uuid.uuid4()), engagement_id=eng.id, title="T", description="d", severity="HIGH",
                status="OPEN", created_by=admin.id)
    db_session.add_all([a, f])
    await db_session.flush()
    db_session.add(AssetPort(id=str(uuid.uuid4()), asset_id=a.id, port_number=443, protocol="TCP"))
    await db_session.flush()
    eng_id = eng.id

    exp = await client.get(f"/engagements/{eng_id}/export")
    assert exp.status_code == 200, exp.text
    src = zipfile.ZipFile(io.BytesIO(exp.content))
    members = {n: src.read(n) for n in src.namelist()}
    data_name = next(n for n, b in members.items() if n.endswith(".json") and b'"assets"' in b and n != "manifest.json")
    data = json.loads(members[data_name])
    # The same host again, as an export from before the index could hold it:
    # a second row (other case) with its own port and a finding link.
    dup_id, port_id = str(uuid.uuid4()), str(uuid.uuid4())
    data["assets"].append({**data["assets"][0], "id": dup_id, "identifier": "WEB01 "})
    data["asset_ports"].append({**data["asset_ports"][0], "id": port_id, "asset_id": dup_id})  # same 443/TCP
    data["asset_ports"].append({**data["asset_ports"][0], "id": str(uuid.uuid4()), "asset_id": dup_id, "port_number": 8443})
    data.setdefault("finding_assets", []).append({"finding_id": data["findings"][0]["id"], "asset_id": dup_id})
    members[data_name] = json.dumps(data).encode()
    from routers.engagements_transfer import _compute_root_digest, _sha256_hex
    manifest = json.loads(members["manifest.json"])
    manifest["digests"] = {n: _sha256_hex(b) for n, b in sorted(members.items()) if n != "manifest.json"}
    manifest["root_digest"] = _compute_root_digest(manifest["digests"])
    members["manifest.json"] = json.dumps(manifest).encode()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for n, b in members.items():
            zf.writestr(n, b)

    imp = await client.post("/engagements/import", files={"file": ("e.zip", buf.getvalue(), "application/zip")})
    assert imp.status_code == 201, imp.text
    new_eng = imp.json()["id"]
    assets = (await db_session.execute(select(Asset).where(Asset.engagement_id == new_eng))).scalars().all()
    assert [x.identifier for x in assets] == ["web01"]
    ports = sorted((await db_session.execute(select(AssetPort.port_number).where(AssetPort.asset_id == assets[0].id))).scalars())
    assert ports == [443, 8443]
    links = (await db_session.execute(select(func.count()).select_from(FindingAsset)
                                      .where(FindingAsset.asset_id == assets[0].id))).scalar_one()
    assert links == 1
