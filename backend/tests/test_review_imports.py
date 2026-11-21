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

