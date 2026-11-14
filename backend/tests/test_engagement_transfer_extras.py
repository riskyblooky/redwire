"""Transfer follow-ups: user-mapping suggestions, the size guard, importer
membership, and the sections added in manifest 1.3 (inline images, spray,
scan history, automation rules)."""

from __future__ import annotations

import json
import uuid

from sqlalchemy import select

from models.finding import Finding
from tests.test_engagement_transfer_roundtrip import _rows, _seed

PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
       b"\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82")


async def _export(client, eng_id):
    r = await client.get(f"/engagements/{eng_id}/export")
    assert r.status_code == 200, r.text
    return r.content


async def _import(client, blob, mapping=None):
    r = await client.post("/engagements/import", data={"user_mapping": json.dumps(mapping or {})},
                          files={"file": ("e.zip", blob, "application/zip")})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def test_preview_suggests_local_users_by_id_then_username(client, db_session, make_user, authenticate_as):
    admin = await make_user(role="admin")
    author, reviewer = await make_user(), await make_user()
    eng = await _seed(db_session, (author, reviewer))
    eng_id = eng.id
    db_session.expunge_all()
    authenticate_as(admin)
    blob = await _export(client, eng_id)

    r = await client.post("/engagements/import/preview", files={"file": ("e.zip", blob, "application/zip")})
    assert r.status_code == 200, r.text
    matched = {u["id"]: u for u in r.json()["matched_users"]}
    assert matched[reviewer.id]["suggested_id"] == reviewer.id and matched[reviewer.id]["match"] == "id"


def _rewrite_archive(blob: bytes, edit) -> bytes:
    """Apply ``edit`` to engagement.json and re-sign the manifest digests."""
    import io
    import zipfile
    from routers.engagements_transfer import _compute_root_digest, _sha256_hex
    src = zipfile.ZipFile(io.BytesIO(blob))
    members = {n: src.read(n) for n in src.namelist() if n != "manifest.json"}
    data = json.loads(members["engagement.json"])
    edit(data)
    members["engagement.json"] = json.dumps(data).encode()
    manifest = json.loads(src.read("manifest.json"))
    manifest["digests"] = {n: _sha256_hex(members[n]) for n in sorted(members)}
    manifest["root_digest"] = _compute_root_digest(manifest["digests"])
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        for n, b in members.items():
            zf.writestr(n, b)
    return out.getvalue()


async def test_preview_suggests_same_username_from_another_instance(client, db_session, make_user, authenticate_as):
    admin = await make_user(role="admin")
    author, reviewer = await make_user(), await make_user()
    eng = await _seed(db_session, (author, reviewer))
    eng_id, uname = eng.id, reviewer.username
    db_session.expunge_all()
    authenticate_as(admin)
    foreign = str(uuid.uuid4())
    blob = _rewrite_archive(await _export(client, eng_id), lambda d: d["users"].update(
        {foreign: {"username": uname.upper(), "full_name": "Elsewhere"}}))
    r = await client.post("/engagements/import/preview", files={"file": ("e.zip", blob, "application/zip")})
    assert r.status_code == 200, r.text
    m = {u["id"]: u for u in r.json()["matched_users"]}[foreign]
    assert (m["suggested_id"], m["match"]) == (reviewer.id, "username")


async def test_export_refuses_what_import_could_not_take(client, db_session, make_user, authenticate_as, monkeypatch):
    import routers.engagements_transfer as tr
    from models.evidence import Evidence
    admin = await make_user(role="admin")
    eng = await _seed(db_session, (await make_user(), await make_user()))
    db_session.add(Evidence(id=str(uuid.uuid4()), engagement_id=eng.id, filename="big.bin",
                            original_filename="big.bin", file_path="nope/big.bin", file_size=5_000_000))
    await db_session.flush()
    eng_id = eng.id
    db_session.expunge_all()
    authenticate_as(admin)
    monkeypatch.setattr(tr, "IMPORT_MAX_ARCHIVE_BYTES", 1_000_000)
    r = await client.get(f"/engagements/{eng_id}/export")
    assert r.status_code == 413, r.text
    assert "ENGAGEMENT_IMPORT_MAX_ARCHIVE_BYTES" in r.json()["detail"]


async def test_importer_joins_team_and_new_sections_round_trip(client, db_session, make_user, authenticate_as):
    from models.associations import EngagementAssignment
    from models.automation import AutomationRule
    from models.markdown_image import MarkdownImage
    from models.permission import EngagementRolePermissions, Permission
    from models.scan_import import ScanImport
    from models.spray import SprayCampaign, SprayResult
    from tests.test_authz_boundaries import _make_engagement_role
    from utils.storage import storage_service

    admin = await make_user(role="admin")
    author, reviewer = await make_user(), await make_user()
    eng = await _seed(db_session, (author, reviewer))
    lead = await _make_engagement_role(db_session, [p.value for p in Permission if p.value.startswith(("engagement", "finding"))]
                                       + [Permission.ENGAGEMENT_MANAGE_MEMBERS.value])

    img_id = str(uuid.uuid4())
    key = f"markdown/{eng.id}/{img_id}.png"
    await storage_service.upload_file(PNG, key, "image/png")
    db_session.add(MarkdownImage(id=img_id, storage_key=key, scope="engagement", engagement_id=eng.id,
                                 content_type="image/png", size_bytes=len(PNG)))
    [f] = await _rows(db_session, Finding, engagement_id=eng.id)
    f.description = f"see ![x](/api/markdown-images/{img_id})"
    camp = SprayCampaign(id=str(uuid.uuid4()), engagement_id=eng.id, name="spring", password_used="Spring2026!")
    db_session.add(camp)
    await db_session.flush()
    db_session.add_all([
        SprayResult(id=str(uuid.uuid4()), campaign_id=camp.id, username="alice", result="success", password="Spring2026!"),
        ScanImport(id=str(uuid.uuid4()), engagement_id=eng.id, source_tool="nmap", hosts_up=3),
        AutomationRule(id=str(uuid.uuid4()), engagement_id=eng.id, name="hook", trigger_type="created_finding",
                       conditions=[], actions=[{"type": "webhook", "url": "https://example.invalid"}],
                       is_enabled=True, created_by=author.id, trigger_count=9),
        AutomationRule(id=str(uuid.uuid4()), engagement_id=eng.id, name="mine", trigger_type="created_finding",
                       conditions=[], actions=[], created_by=author.id, owner_user_id=author.id),
    ])
    await db_session.flush()
    eng_id = eng.id
    db_session.expunge_all()
    authenticate_as(admin)

    blob = await _export(client, eng_id)
    new_id = await _import(client, blob)  # nobody mapped
    db = db_session

    # Importer is on the team with the member-managing role.
    [a] = await _rows(db, EngagementAssignment, engagement_id=new_id)
    perms = (await db.execute(select(EngagementRolePermissions.permissions)
                              .where(EngagementRolePermissions.role_id == a.role_id))).scalar_one()
    assert a.user_id == admin.id and Permission.ENGAGEMENT_MANAGE_MEMBERS.value in perms
    assert lead  # the seeded role exists so a manager role is available

    # Inline image: new row + object, and the finding text points at it.
    [img] = await _rows(db, MarkdownImage, engagement_id=new_id)
    assert img.id != img_id and await storage_service.download_file(img.storage_key) == PNG
    [nf] = await _rows(db, Finding, engagement_id=new_id)
    assert nf.description == f"see ![x](/api/markdown-images/{img.id})"

    # Spray (secrets re-encrypted on bind, readable through the ORM), scans.
    [nc] = await _rows(db, SprayCampaign, engagement_id=new_id)
    assert nc.password_used == "Spring2026!"
    [nr] = await _rows(db, SprayResult, campaign_id=nc.id)
    assert (nr.username, nr.password, nr.result) == ("alice", "Spring2026!", "success")
    [ns] = await _rows(db, ScanImport, engagement_id=new_id)
    assert (ns.source_tool, ns.hosts_up) == ("nmap", 3)

    # Rules arrive disabled with fresh counters; an unmapped owner's
    # personal rule is not imported.
    rules = await _rows(db, AutomationRule, engagement_id=new_id)
    assert [(r.name, r.is_enabled, r.trigger_count) for r in rules] == [("hook", False, 0)]

    # Mapping the owner brings the personal rule along, still disabled.
    newer = await _import(client, blob, {author.id: author.id})
    names = sorted((r.name, r.owner_user_id, r.is_enabled) for r in await _rows(db, AutomationRule, engagement_id=newer))
    assert names == [("hook", None, False), ("mine", author.id, False)]


async def test_export_flags_spray_secrets(client, db_session, make_user, authenticate_as):
    from models.spray import SprayCampaign
    from tests.test_authz_boundaries import _make_engagement
    eng = await _make_engagement(db_session)
    db_session.add(SprayCampaign(id=str(uuid.uuid4()), engagement_id=eng.id, name="c", password_used="pw"))
    await db_session.flush()
    eng_id = eng.id
    db_session.expunge_all()
    authenticate_as(await make_user(role="admin"))
    r = await client.get(f"/engagements/{eng_id}/export/preview")
    assert r.json()["contains_plaintext_secrets"] is True
