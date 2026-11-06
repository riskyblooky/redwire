"""Asset types are canonicalized onto the configured types on every write
(utils/asset_types.py), so the edit form's Type dropdown can show them."""

from __future__ import annotations

import io
import uuid

import pytest
from sqlalchemy import select

from models.configurable_type import ConfigurableType
from models.engagement import Engagement
from utils.asset_types import canonical_name

DEFAULTS = ["IP Address", "Domain", "URL", "Application", "Server", "Network", "Other"]


def test_canonical_name_mapping():
    assert canonical_name("IP_ADDRESS", DEFAULTS) == "IP Address"
    assert canonical_name("ip address", DEFAULTS) == "IP Address"
    assert canonical_name("ip", DEFAULTS) == "IP Address"
    assert canonical_name("host", DEFAULTS) == "Server"
    assert canonical_name("web_application", DEFAULTS) == "Application"
    assert canonical_name("network-device", DEFAULTS) == "Network"
    assert canonical_name("DOMAIN", DEFAULTS) == "Domain"
    assert canonical_name("Cloud Resource", DEFAULTS) is None
    assert canonical_name("", DEFAULTS) is None
    # An alias whose default type an admin removed doesn't resolve.
    assert canonical_name("host", ["IP Address", "Domain"]) is None
    # Custom configured types match by name.
    assert canonical_name("cloud_resource", DEFAULTS + ["Cloud Resource"]) == "Cloud Resource"


@pytest.fixture
async def asset_types(db_session):
    have = set((await db_session.execute(
        select(ConfigurableType.name).where(ConfigurableType.category == "asset")
    )).scalars().all())
    for i, name in enumerate(DEFAULTS):
        if name not in have:
            db_session.add(ConfigurableType(id=str(uuid.uuid4()), category="asset", name=name,
                                            is_system=True, sort_order=i))
    await db_session.flush()


async def _engagement(db, make_user, authenticate_as):
    admin = await make_user(role="admin", username=f"at_ad_{uuid.uuid4().hex[:6]}")
    authenticate_as(admin)
    eng = Engagement(id=str(uuid.uuid4()), name="Types", client_name="ACME",
                     engagement_type="external_pentest", created_by=admin.id)
    db.add(eng)
    await db.flush()
    return eng


async def test_create_and_update_canonicalize(client, db_session, make_user, authenticate_as, asset_types):
    eng = await _engagement(db_session, make_user, authenticate_as)
    r = await client.post("/assets", json={"engagement_id": eng.id, "name": "dc01",
                                           "asset_type": "IP_ADDRESS", "identifier": "10.0.0.5"})
    assert r.status_code == 201, r.text
    assert r.json()["asset_type"] == "IP Address"

    u = await client.put(f"/assets/{r.json()['id']}", json={"asset_type": "host"})
    assert u.status_code == 200, u.text
    assert u.json()["asset_type"] == "Server"

    bad = await client.put(f"/assets/{r.json()['id']}", json={"asset_type": "spaceship"})
    assert bad.status_code == 422
    assert "Valid types" in bad.json()["detail"]
    bad = await client.post("/assets", json={"engagement_id": eng.id, "name": "x",
                                             "asset_type": "spaceship", "identifier": "x"})
    assert bad.status_code == 422


async def test_csv_import_maps_and_falls_back(client, db_session, make_user, authenticate_as, asset_types):
    eng = await _engagement(db_session, make_user, authenticate_as)
    csv_body = ("name,asset_type,identifier\n"
                "a,web_application,https://a.example\n"
                "b,spaceship,b.example\n"
                "c,Domain,c.example\n")
    r = await client.post("/assets/import", data={"engagement_id": eng.id},
                          files={"file": ("assets.csv", io.BytesIO(csv_body.encode()), "text/csv")})
    assert r.status_code == 200, r.text
    got = await client.get("/assets", params={"engagement_id": eng.id})
    types = {a["name"]: a["asset_type"] for a in got.json()["items"]}
    assert types == {"a": "Application", "b": "Other", "c": "Domain"}
