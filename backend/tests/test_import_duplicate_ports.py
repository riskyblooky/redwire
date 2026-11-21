"""A scan file that names the same host (or the same port) more than once
imports cleanly instead of tripping the asset_ports unique constraint."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from tests.test_authz_boundaries import _make_engagement

NMAP = b"""<?xml version="1.0"?>
<nmaprun scanner="nmap" args="nmap -sV 10.9.9.9">
  <host><status state="up"/><address addr="10.9.9.9" addrtype="ipv4"/>
    <ports>
      <port protocol="tcp" portid="80"><state state="open"/><service name="http"/></port>
      <port protocol="tcp" portid="80"><state state="open"/><service name="http"/></port>
    </ports>
  </host>
  <host><status state="up"/><address addr="10.9.9.9" addrtype="ipv4"/>
    <ports>
      <port protocol="tcp" portid="80"><state state="open"/><service name="http"/></port>
      <port protocol="tcp" portid="443"><state state="open"/><service name="https"/></port>
    </ports>
  </host>
</nmaprun>
"""


async def _ports(db, eng_id):
    from models.asset import Asset
    from models.asset_port import AssetPort

    assets = (await db.execute(select(func.count()).select_from(Asset).where(Asset.engagement_id == eng_id))).scalar()
    ports = (await db.execute(
        select(AssetPort.port_number).join(Asset, Asset.id == AssetPort.asset_id).where(Asset.engagement_id == eng_id)
    )).scalars().all()
    return assets, sorted(ports)


@pytest.mark.parametrize("path", ["/imports/commit", "/assets/import"])
async def test_repeated_host_and_port(path, client, db_session, make_user, authenticate_as):
    admin = await make_user(role="admin")
    eng = await _make_engagement(db_session)
    authenticate_as(admin)

    r = await client.post(path, data={"engagement_id": eng.id},
                          files={"file": ("scan.xml", NMAP, "application/xml")})

    assert r.status_code == 200, r.text
    assert await _ports(db_session, eng.id) == (1, [80, 443])

    # Importing the same file again adds nothing.
    r = await client.post(path, data={"engagement_id": eng.id},
                          files={"file": ("scan.xml", NMAP, "application/xml")})
    assert r.status_code == 200, r.text
    assert await _ports(db_session, eng.id) == (1, [80, 443])
