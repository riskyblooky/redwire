"""Spray preview: the upload is read capped, and the raw log is saved to
the vault once — not again on every preview of the same file."""

from __future__ import annotations

from sqlalchemy import func, select

from models.vault import VaultItem
from tests.test_authz_boundaries import _make_engagement

LOG = (b"SMB   10.0.0.5   445  DC01   [-] lab.local\\alice:Summer2025! STATUS_LOGON_FAILURE\n"
       b"SMB   10.0.0.5   445  DC01   [+] lab.local\\bob:Summer2025!\n")


async def test_preview_saves_one_vault_copy(client, db_session, make_user, authenticate_as, monkeypatch):
    authenticate_as(await make_user(role="admin"))
    eng = await _make_engagement(db_session)
    for _ in range(2):
        r = await client.post("/spray/import", data={"engagement_id": eng.id},
                              files={"file": ("nxc.log", LOG, "text/plain")})
        assert r.status_code == 200, r.text
    n = (await db_session.execute(select(func.count()).select_from(VaultItem)
                                  .where(VaultItem.engagement_id == eng.id))).scalar()
    assert n == 1

    monkeypatch.setenv("SCANNER_IMPORT_MAX_BYTES", "10")
    r = await client.post("/spray/import", data={"engagement_id": eng.id},
                          files={"file": ("nxc.log", LOG, "text/plain")})
    assert r.status_code == 413
