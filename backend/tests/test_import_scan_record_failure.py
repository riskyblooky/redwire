"""A failure saving the scan-import record is best-effort: it used to be
swallowed without a rollback, leaving the session failed so the raw-file
attachment after it broke too (and the import returned a 500)."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from tests.test_authz_boundaries import _make_engagement
from tests.test_parsers_httpx_nxc import NXC_LOG


async def test_import_survives_scan_record_failure(client, db_session, make_user, authenticate_as, monkeypatch):
    import routers.imports as imports
    from models.evidence import Evidence
    from models.scan_import import ScanImport
    from utils.storage import storage_service

    async def fake_upload(content, name, content_type=None):
        return name
    monkeypatch.setattr(storage_service, "upload_file", fake_upload)
    # A dangling engagement id makes the record's flush fail (FK violation).
    monkeypatch.setattr(imports, "ScanImport", lambda **kw: ScanImport(**{**kw, "engagement_id": str(uuid.uuid4())}))

    admin = await make_user(role="admin")
    eng = await _make_engagement(db_session)
    authenticate_as(admin)
    r = await client.post("/imports/commit", data={"engagement_id": eng.id},
                          files={"file": ("nxc.log", NXC_LOG, "text/plain")})
    assert r.status_code == 200, r.text
    assert r.json().get("scan_import_id") is None
    saved = (await db_session.execute(select(Evidence).where(Evidence.engagement_id == eng.id))).scalars().all()
    assert [e.original_filename for e in saved] == ["nxc.log"]
