"""Review sweep: imports, parsers, vault."""

from __future__ import annotations

import uuid

from sqlalchemy import select

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
