"""
Engagement Export / Import
--------------------------
GET  /engagements/{id}/export  →  ZIP download
POST /engagements/import       →  ZIP upload → new engagement
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from database import get_db
from auth.dependencies import get_current_user
from models.user import User, UserRole
from utils.storage import storage_service

import json
import uuid
import zipfile
import io
import os
import traceback
from datetime import datetime

router = APIRouter(prefix="/engagements", tags=["engagements"])

# ── helpers ──────────────────────────────────────────────────────────────

def _dt(v):
    """Serialize datetime → ISO string or None."""
    if isinstance(v, datetime):
        return v.isoformat()
    return v


def _row_dict(obj, fields: list[str]) -> dict:
    """Extract selected columns from an ORM object."""
    d = {}
    for f in fields:
        v = getattr(obj, f, None)
        if isinstance(v, datetime):
            v = v.isoformat()
        elif hasattr(v, 'value'):  # Enum
            v = v.value
        d[f] = v
    return d

# ═════════════════════════════════════════════════════════════════════════
#  EXPORT
# ═════════════════════════════════════════════════════════════════════════

@router.get("/{engagement_id}/export")
async def export_engagement(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export an engagement as a ZIP archive with all data and attachments."""
    if current_user.role not in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]:
        raise HTTPException(status_code=403, detail="Admin or Team Lead role required")

    # ── load engagement ──────────────────────────────────────────────
    from models.engagement import Engagement
    result = await db.execute(select(Engagement).where(Engagement.id == engagement_id))
    eng = result.scalar_one_or_none()
    if not eng:
        raise HTTPException(status_code=404, detail="Engagement not found")

    eng_fields = [
        "id", "name", "client_name", "engagement_type", "status",
        "description", "scope", "objectives", "start_date", "end_date",
        "created_by", "updated_by", "created_at", "updated_at",
    ]
    data: dict = {"engagement": _row_dict(eng, eng_fields)}

    # ── Collect user IDs for username resolution ─────────────────────
    user_ids_set: set[str] = set()
    def _collect_user_ids(obj, *fields):
        for f in fields:
            uid = getattr(obj, f, None)
            if uid:
                user_ids_set.add(uid)

    # ── findings ─────────────────────────────────────────────────────
    from models.finding import Finding, Tag
    res = await db.execute(
        select(Finding)
        .options(selectinload(Finding.tags), selectinload(Finding.assets), selectinload(Finding.testcases))
        .where(Finding.engagement_id == engagement_id)
    )
    findings = res.scalars().all()
    finding_fields = [
        "id", "title", "category", "description", "severity", "status",
        "cvss_score", "cvss_vector", "impact", "technical_details",
        "steps_to_reproduce", "mitigations", "references",
        "created_by", "updated_by", "created_at", "updated_at",
    ]
    data["findings"] = [_row_dict(f, finding_fields) for f in findings]
    for f in findings:
        _collect_user_ids(f, "created_by", "updated_by")

    # Finding → Asset M2M (with remediation data)
    from models.associations import FindingAsset
    fa_res = await db.execute(
        select(FindingAsset).where(
            FindingAsset.finding_id.in_([f.id for f in findings]) if findings else False
        )
    )
    fa_rows = fa_res.scalars().all() if findings else []
    data["finding_assets"] = [
        _row_dict(r, ["finding_id", "asset_id", "port_ids", "remediated", "remediated_at"])
        for r in fa_rows
    ]

    # Finding → TestCase M2M
    from models.associations import FindingTestCase
    ft_res = await db.execute(
        select(FindingTestCase).where(
            FindingTestCase.finding_id.in_([f.id for f in findings]) if findings else False
        )
    )
    ft_rows = ft_res.scalars().all() if findings else []
    data["finding_testcases"] = [
        _row_dict(r, ["finding_id", "testcase_id"]) for r in ft_rows
    ]

    # ── tags (only those used by this engagement's entities) ─────────
    tag_ids_set: set[str] = set()
    for f in findings:
        for t in f.tags:
            tag_ids_set.add(t.id)

    # Also collect from testcases later — we'll gather during testcase export
    # For now, collect finding tags
    from models.associations import FindingTag
    ft_tag_res = await db.execute(
        select(FindingTag).where(
            FindingTag.finding_id.in_([f.id for f in findings]) if findings else False
        )
    )
    data["finding_tags"] = [
        _row_dict(r, ["finding_id", "tag_id"]) for r in (ft_tag_res.scalars().all() if findings else [])
    ]

    # ── assets ───────────────────────────────────────────────────────
    from models.asset import Asset
    from models.asset_port import AssetPort
    a_res = await db.execute(select(Asset).where(Asset.engagement_id == engagement_id))
    assets = a_res.scalars().all()
    asset_fields = [
        "id", "name", "asset_type", "identifier", "description", "notes",
        "is_pwned", "is_scanned", "in_scope",
        "created_by", "updated_by", "created_at", "updated_at",
    ]
    data["assets"] = [_row_dict(a, asset_fields) for a in assets]
    for a in assets:
        _collect_user_ids(a, "created_by", "updated_by")

    # Ports
    p_res = await db.execute(
        select(AssetPort).where(
            AssetPort.asset_id.in_([a.id for a in assets]) if assets else False
        )
    )
    ports = p_res.scalars().all() if assets else []
    data["asset_ports"] = [
        _row_dict(p, ["id", "asset_id", "port_number", "protocol", "service_name", "state", "version"])
        for p in ports
    ]

    # ── testcases ────────────────────────────────────────────────────
    from models.testcase import TestCase
    tc_res = await db.execute(
        select(TestCase).options(selectinload(TestCase.tags))
        .where(TestCase.engagement_id == engagement_id)
    )
    testcases = tc_res.scalars().all()
    tc_fields = [
        "id", "parent_id", "title", "category", "description", "steps",
        "expected_result", "actual_result", "is_executed", "is_successful", "notes",
        "created_by", "updated_by", "created_at", "updated_at",
    ]
    data["testcases"] = [_row_dict(tc, tc_fields) for tc in testcases]
    for tc in testcases:
        _collect_user_ids(tc, "created_by", "updated_by")

    # Testcase tags
    for tc in testcases:
        for t in tc.tags:
            tag_ids_set.add(t.id)

    from models.associations import TestCaseTag
    tct_res = await db.execute(
        select(TestCaseTag).where(
            TestCaseTag.testcase_id.in_([tc.id for tc in testcases]) if testcases else False
        )
    )
    data["testcase_tags"] = [
        _row_dict(r, ["testcase_id", "tag_id"]) for r in (tct_res.scalars().all() if testcases else [])
    ]

    # Testcase → Asset M2M
    from models.associations import TestCaseAsset
    tca_res = await db.execute(
        select(TestCaseAsset).where(
            TestCaseAsset.testcase_id.in_([tc.id for tc in testcases]) if testcases else False
        )
    )
    data["testcase_assets"] = [
        _row_dict(r, ["testcase_id", "asset_id", "port_ids"]) for r in (tca_res.scalars().all() if testcases else [])
    ]

    # ── tags (fetch actual tag objects) ──────────────────────────────
    if tag_ids_set:
        tags_res = await db.execute(select(Tag).where(Tag.id.in_(tag_ids_set)))
        tags = tags_res.scalars().all()
    else:
        tags = []
    data["tags"] = [_row_dict(t, ["id", "name", "color", "created_at"]) for t in tags]

    # ── evidence ─────────────────────────────────────────────────────
    from models.evidence import Evidence
    ev_res = await db.execute(select(Evidence).where(
        (Evidence.engagement_id == engagement_id) |
        (Evidence.finding_id.in_([f.id for f in findings]) if findings else False) |
        (Evidence.testcase_id.in_([tc.id for tc in testcases]) if testcases else False)
    ))
    evidence_list = ev_res.scalars().all()
    ev_fields = [
        "id", "finding_id", "testcase_id", "engagement_id",
        "filename", "original_filename", "file_path", "file_size",
        "mime_type", "description", "include_in_report",
        "created_by", "updated_by", "created_at", "updated_at",
    ]
    data["evidence"] = [_row_dict(e, ev_fields) for e in evidence_list]
    for e in evidence_list:
        _collect_user_ids(e, "created_by", "updated_by")

    # ── threads & comments ───────────────────────────────────────────
    from models.discussion import Thread, Comment
    th_res = await db.execute(
        select(Thread).options(selectinload(Thread.comments))
        .where(Thread.engagement_id == engagement_id)
    )
    threads = th_res.scalars().all()
    data["threads"] = [
        _row_dict(t, ["id", "resource_type", "resource_id", "title", "is_resolved", "created_by", "created_at"])
        for t in threads
    ]
    for t in threads:
        _collect_user_ids(t, "created_by")
    all_comments = []
    for t in threads:
        for c in t.comments:
            all_comments.append(_row_dict(c, [
                "id", "thread_id", "content", "is_resolvable", "is_resolved",
                "resolved_by", "resolved_at", "created_by", "created_at",
            ]))
            _collect_user_ids(c, "created_by", "resolved_by")
    data["comments"] = all_comments

    # ── activity logs ────────────────────────────────────────────────
    from models.discussion import ActivityLog
    al_res = await db.execute(select(ActivityLog).where(ActivityLog.engagement_id == engagement_id))
    activity_logs = al_res.scalars().all()
    data["activity_logs"] = [
        _row_dict(a, ["id", "user_id", "action", "resource_type", "resource_id", "resource_name", "details", "created_at"])
        for a in activity_logs
    ]
    for a in activity_logs:
        _collect_user_ids(a, "user_id")

    # ── vault items ──────────────────────────────────────────────────
    from models.vault import VaultItem
    vi_res = await db.execute(
        select(VaultItem).options(selectinload(VaultItem.findings), selectinload(VaultItem.testcases))
        .where(VaultItem.engagement_id == engagement_id)
    )
    vault_items = vi_res.scalars().all()
    vi_fields = [
        "id", "name", "item_type", "username", "password", "note",
        "file_path", "filename", "description",
        "created_by", "updated_by", "created_at", "updated_at",
    ]
    data["vault_items"] = [_row_dict(v, vi_fields) for v in vault_items]
    for v in vault_items:
        _collect_user_ids(v, "created_by", "updated_by")

    # Vault M2M
    from models.associations import VaultItemFinding, VaultItemTestCase
    vif_res = await db.execute(
        select(VaultItemFinding).where(
            VaultItemFinding.vault_item_id.in_([v.id for v in vault_items]) if vault_items else False
        )
    )
    data["vault_item_findings"] = [
        _row_dict(r, ["vault_item_id", "finding_id"]) for r in (vif_res.scalars().all() if vault_items else [])
    ]
    vitc_res = await db.execute(
        select(VaultItemTestCase).where(
            VaultItemTestCase.vault_item_id.in_([v.id for v in vault_items]) if vault_items else False
        )
    )
    data["vault_item_testcases"] = [
        _row_dict(r, ["vault_item_id", "testcase_id"]) for r in (vitc_res.scalars().all() if vault_items else [])
    ]

    # ── cleanup artifacts ────────────────────────────────────────────
    from models.cleanup_artifact import CleanupArtifact
    ca_res = await db.execute(
        select(CleanupArtifact)
        .options(
            selectinload(CleanupArtifact.findings),
            selectinload(CleanupArtifact.testcases),
            selectinload(CleanupArtifact.assets),
        )
        .where(CleanupArtifact.engagement_id == engagement_id)
    )
    cleanup_artifacts = ca_res.scalars().all()
    ca_fields = [
        "id", "title", "artifact_type", "status", "location",
        "description", "cleanup_notes", "cleaned_at", "cleaned_by",
        "created_by", "updated_by", "created_at", "updated_at",
    ]
    data["cleanup_artifacts"] = [_row_dict(ca, ca_fields) for ca in cleanup_artifacts]
    for ca in cleanup_artifacts:
        _collect_user_ids(ca, "created_by", "updated_by", "cleaned_by")

    # Cleanup M2M
    from models.associations import CleanupArtifactFinding, CleanupArtifactTestCase, CleanupArtifactAsset
    caf_res = await db.execute(
        select(CleanupArtifactFinding).where(
            CleanupArtifactFinding.cleanup_artifact_id.in_([ca.id for ca in cleanup_artifacts]) if cleanup_artifacts else False
        )
    )
    data["cleanup_artifact_findings"] = [
        _row_dict(r, ["cleanup_artifact_id", "finding_id"]) for r in (caf_res.scalars().all() if cleanup_artifacts else [])
    ]
    catc_res = await db.execute(
        select(CleanupArtifactTestCase).where(
            CleanupArtifactTestCase.cleanup_artifact_id.in_([ca.id for ca in cleanup_artifacts]) if cleanup_artifacts else False
        )
    )
    data["cleanup_artifact_testcases"] = [
        _row_dict(r, ["cleanup_artifact_id", "testcase_id"]) for r in (catc_res.scalars().all() if cleanup_artifacts else [])
    ]
    caas_res = await db.execute(
        select(CleanupArtifactAsset).where(
            CleanupArtifactAsset.cleanup_artifact_id.in_([ca.id for ca in cleanup_artifacts]) if cleanup_artifacts else False
        )
    )
    data["cleanup_artifact_assets"] = [
        _row_dict(r, ["cleanup_artifact_id", "asset_id"]) for r in (caas_res.scalars().all() if cleanup_artifacts else [])
    ]

    # ── notes ────────────────────────────────────────────────────────
    from models.note import Note
    note_res = await db.execute(select(Note).where(Note.engagement_id == engagement_id))
    notes = note_res.scalars().all()
    data["notes"] = [
        _row_dict(n, ["id", "title", "content", "created_by", "updated_by", "created_at", "updated_at"]) for n in notes
    ]
    for n in notes:
        _collect_user_ids(n, "created_by", "updated_by")

    # Note M2M
    from models.associations import NoteAsset, NoteTestCase, NoteFinding, NoteVaultItem, NoteCleanupArtifact
    for assoc_cls, key, fk_col in [
        (NoteFinding, "note_findings", "note_id"),
        (NoteTestCase, "note_testcases", "note_id"),
        (NoteAsset, "note_assets", "note_id"),
        (NoteVaultItem, "note_vault_items", "note_id"),
        (NoteCleanupArtifact, "note_cleanup_artifacts", "note_id"),
    ]:
        cols = [c.key for c in assoc_cls.__table__.columns]
        assoc_res = await db.execute(
            select(assoc_cls).where(
                getattr(assoc_cls, fk_col).in_([n.id for n in notes]) if notes else False
            )
        )
        data[key] = [_row_dict(r, cols) for r in (assoc_res.scalars().all() if notes else [])]

    # ── attacker nodes & edges ───────────────────────────────────────
    from models.attacker_node import AttackerNode, AttackerNodeEdge
    an_res = await db.execute(select(AttackerNode).where(AttackerNode.engagement_id == engagement_id))
    attacker_nodes = an_res.scalars().all()
    data["attacker_nodes"] = [
        _row_dict(an, ["id", "name", "point_of_presence", "description", "created_at"]) for an in attacker_nodes
    ]
    ane_res = await db.execute(
        select(AttackerNodeEdge).where(
            AttackerNodeEdge.attacker_node_id.in_([an.id for an in attacker_nodes]) if attacker_nodes else False
        )
    )
    data["attacker_node_edges"] = [
        _row_dict(r, ["id", "attacker_node_id", "target_node_id", "target_node_type"])
        for r in (ane_res.scalars().all() if attacker_nodes else [])
    ]

    # ── attack graph layout ──────────────────────────────────────────
    from models.attack_graph_layout import AttackGraphLayout
    agl_res = await db.execute(select(AttackGraphLayout).where(AttackGraphLayout.engagement_id == engagement_id))
    agl = agl_res.scalar_one_or_none()
    data["attack_graph_layout"] = _row_dict(agl, ["id", "positions", "pinned_at"]) if agl else None

    # ── report layouts ───────────────────────────────────────────────
    from models.report_layout import ReportLayout, ReportSection
    rl_res = await db.execute(
        select(ReportLayout).options(selectinload(ReportLayout.sections))
        .where(ReportLayout.engagement_id == engagement_id)
    )
    report_layouts = rl_res.scalars().all()
    data["report_layouts"] = []
    for rl in report_layouts:
        rl_dict = _row_dict(rl, ["id", "name", "is_default", "created_at", "updated_at"])
        rl_dict["sections"] = [
            _row_dict(s, ["id", "section_type", "title", "content", "sort_order"]) for s in rl.sections
        ]
        data["report_layouts"].append(rl_dict)
    for rl in report_layouts:
        _collect_user_ids(rl, "created_by", "updated_by")
    _collect_user_ids(eng, "created_by", "updated_by")

    # ── resolve user IDs → usernames ─────────────────────────────────
    user_ids_set.discard(None)
    user_lookup: dict[str, dict] = {}
    if user_ids_set:
        users_res = await db.execute(select(User).where(User.id.in_(user_ids_set)))
        for u in users_res.scalars().all():
            user_lookup[u.id] = {
                "username": u.username,
                "full_name": u.full_name or u.username,
                "email": u.email,
            }
    data["users"] = user_lookup

    # ═══════════════════════════════════════════════════════════════════
    # Build ZIP in memory
    # ═══════════════════════════════════════════════════════════════════
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        # manifest
        manifest = {
            "version": "1.0",
            "exported_at": datetime.utcnow().isoformat(),
            "engagement_name": eng.name,
            "source": "redwire",
        }
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))

        # data
        zf.writestr("engagement.json", json.dumps(data, indent=2, default=str))

        # attachments — evidence files
        for ev in evidence_list:
            if ev.file_path:
                try:
                    file_bytes = await storage_service.download_file(ev.file_path)
                    zf.writestr(f"attachments/{ev.file_path}", file_bytes)
                except Exception:
                    pass  # skip missing files

        # attachments — vault files
        for vi in vault_items:
            if vi.file_path:
                try:
                    file_bytes = await storage_service.download_file(vi.file_path)
                    zf.writestr(f"attachments/{vi.file_path}", file_bytes)
                except Exception:
                    pass

    zip_buf.seek(0)
    safe_name = eng.name.replace(" ", "_").replace("/", "-")[:50]
    filename = f"redwire_export_{safe_name}_{datetime.utcnow().strftime('%Y%m%d')}.zip"

    return StreamingResponse(
        zip_buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

# ═════════════════════════════════════════════════════════════════════════
#  IMPORT PREVIEW — identify unmatched users before importing
# ═════════════════════════════════════════════════════════════════════════

@router.post("/import/preview")
async def preview_import(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Preview a ZIP archive: return matched & unmatched users so the admin can map them."""
    if current_user.role not in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]:
        raise HTTPException(status_code=403, detail="Admin or Team Lead role required")

    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="File must be a .zip archive")

    content = await file.read()
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Invalid ZIP file")

    if "manifest.json" not in zf.namelist():
        raise HTTPException(status_code=400, detail="Missing manifest.json in archive")
    manifest = json.loads(zf.read("manifest.json"))
    if manifest.get("source") != "redwire":
        raise HTTPException(status_code=400, detail="Archive is not a RedWire export")

    if "engagement.json" not in zf.namelist():
        raise HTTPException(status_code=400, detail="Missing engagement.json in archive")
    data = json.loads(zf.read("engagement.json"))
    zf.close()

    exported_users: dict = data.get("users", {})
    engagement_name = data.get("engagement", {}).get("name", "Unknown")

    # Check which user IDs exist locally
    matched = []
    unmatched = []
    if exported_users:
        exported_ids = list(exported_users.keys())
        existing_res = await db.execute(select(User).where(User.id.in_(exported_ids)))
        local_matches = {u.id: u for u in existing_res.scalars().all()}

        for uid, info in exported_users.items():
            entry = {
                "id": uid,
                "username": info.get("username", "unknown"),
                "full_name": info.get("full_name", ""),
                "email": info.get("email", ""),
            }
            if uid in local_matches:
                lu = local_matches[uid]
                entry["local_username"] = lu.username
                entry["local_full_name"] = lu.full_name or lu.username
                matched.append(entry)
            else:
                unmatched.append(entry)

    # Fetch all local users for the mapping dropdown
    all_users_res = await db.execute(select(User).where(User.is_active == True))
    local_users = [
        {
            "id": u.id,
            "username": u.username,
            "full_name": u.full_name or u.username,
        }
        for u in all_users_res.scalars().all()
    ]

    return {
        "engagement_name": engagement_name,
        "matched_users": matched,
        "unmatched_users": unmatched,
        "local_users": local_users,
    }

# ═════════════════════════════════════════════════════════════════════════
#  IMPORT
# ═════════════════════════════════════════════════════════════════════════

@router.post("/import", status_code=status.HTTP_201_CREATED)
async def import_engagement(
    file: UploadFile = File(...),
    user_mapping: str = Form(default="{}"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Import an engagement from a ZIP archive. Accepts optional user_mapping JSON."""
    if current_user.role not in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]:
        raise HTTPException(status_code=403, detail="Admin or Team Lead role required")

    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="File must be a .zip archive")

    content = await file.read()
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Invalid ZIP file")

    # Read manifest
    if "manifest.json" not in zf.namelist():
        raise HTTPException(status_code=400, detail="Missing manifest.json in archive")
    manifest = json.loads(zf.read("manifest.json"))
    if manifest.get("source") != "redwire":
        raise HTTPException(status_code=400, detail="Archive is not a RedWire export")

    # Read data
    if "engagement.json" not in zf.namelist():
        raise HTTPException(status_code=400, detail="Missing engagement.json in archive")
    data = json.loads(zf.read("engagement.json"))

    # ── Resolve users: match exported user IDs to local users ────────
    # Parse manual user mapping from form data
    try:
        manual_mapping: dict[str, str] = json.loads(user_mapping) if user_mapping else {}
    except json.JSONDecodeError:
        manual_mapping = {}

    exported_users: dict = data.get("users", {})
    local_user_ids: set[str] = set()
    if exported_users:
        exported_ids = list(exported_users.keys())
        existing_users_res = await db.execute(
            select(User.id).where(User.id.in_(exported_ids))
        )
        local_user_ids = {row[0] for row in existing_users_res.all()}

    # Also validate that manual mapping targets exist
    if manual_mapping:
        mapping_targets = list(manual_mapping.values())
        valid_targets_res = await db.execute(
            select(User.id).where(User.id.in_(mapping_targets))
        )
        valid_targets = {row[0] for row in valid_targets_res.all()}
    else:
        valid_targets = set()

    def resolve_user(original_user_id: str | None) -> str:
        """Return mapped user, auto-matched user, or fallback to importer."""
        if not original_user_id:
            return current_user.id
        # 1. Check manual mapping first
        if original_user_id in manual_mapping:
            mapped = manual_mapping[original_user_id]
            if mapped in valid_targets:
                return mapped
        # 2. Fallback. Do NOT auto-trust user IDs from the archive
        #    even if they exist locally — they are attacker-controlled
        #    and would let the importer attribute records to anyone.
        return current_user.id

    # ── ID mapping: old_id → new_id ──────────────────────────────────
    id_map: dict[str, str] = {}

    def new_id(old_id: str | None) -> str | None:
        if not old_id:
            return None
        if old_id not in id_map:
            id_map[old_id] = str(uuid.uuid4())
        return id_map[old_id]

    def remap(old_id: str | None) -> str | None:
        if not old_id:
            return None
        # Only return IDs created in this import. An old_id never
        # registered via new_id() points outside this bundle; falling
        # through to the raw value allowed cross-engagement FK injection.
        return id_map.get(old_id)

    def parse_dt(v):
        if not v:
            return None
        if isinstance(v, datetime):
            return v
        try:
            return datetime.fromisoformat(v)
        except Exception:
            return None

    try:
        # ── 1. Engagement ────────────────────────────────────────────
        from models.engagement import Engagement
        eng_data = data["engagement"]
        eng_new_id = new_id(eng_data["id"])

        new_eng = Engagement(
            id=eng_new_id,
            name=eng_data["name"] + " (imported)",
            client_name=eng_data.get("client_name", ""),
            engagement_type=eng_data.get("engagement_type", "Other"),
            status=eng_data.get("status", "PLANNING"),
            description=eng_data.get("description"),
            scope=eng_data.get("scope"),
            objectives=eng_data.get("objectives"),
            start_date=parse_dt(eng_data.get("start_date")),
            end_date=parse_dt(eng_data.get("end_date")),
            created_by=resolve_user(eng_data.get("created_by")),
            updated_by=resolve_user(eng_data.get("updated_by")),
            # Don't set client_id — the source client likely doesn't exist here
        )
        db.add(new_eng)
        await db.flush()

        # ── 2. Tags — upsert by name ────────────────────────────────
        from models.finding import Tag
        for tag_data in data.get("tags", []):
            old_tag_id = tag_data["id"]
            # Check if tag with same name exists
            existing = await db.execute(select(Tag).where(Tag.name == tag_data["name"]))
            existing_tag = existing.scalar_one_or_none()
            if existing_tag:
                id_map[old_tag_id] = existing_tag.id
            else:
                new_tag_id = new_id(old_tag_id)
                db.add(Tag(
                    id=new_tag_id,
                    name=tag_data["name"],
                    color=tag_data.get("color"),
                    created_at=parse_dt(tag_data.get("created_at")) or datetime.utcnow(),
                ))
                await db.flush()

        # ── 3. Assets ────────────────────────────────────────────────
        from models.asset import Asset
        for a in data.get("assets", []):
            db.add(Asset(
                id=new_id(a["id"]),
                engagement_id=eng_new_id,
                name=a["name"],
                asset_type=a.get("asset_type", "Other"),
                identifier=a.get("identifier", ""),
                description=a.get("description"),
                notes=a.get("notes"),
                is_pwned=a.get("is_pwned", False),
                is_scanned=a.get("is_scanned", False),
                in_scope=a.get("in_scope", True),
                created_by=resolve_user(a.get("created_by")),
                updated_by=resolve_user(a.get("updated_by")),
                created_at=parse_dt(a.get("created_at")) or datetime.utcnow(),
            ))
        await db.flush()

        # ── 3b. Asset Ports ──────────────────────────────────────────
        from models.asset_port import AssetPort
        for p in data.get("asset_ports", []):
            asset_id = remap(p["asset_id"])
            if asset_id is None:
                continue
            db.add(AssetPort(
                id=new_id(p["id"]),
                asset_id=asset_id,
                port_number=p["port_number"],
                protocol=p.get("protocol", "TCP"),
                service_name=p.get("service_name"),
                state=p.get("state", "OPEN"),
                version=p.get("version"),
            ))
        await db.flush()

        # ── 4. Findings ──────────────────────────────────────────────
        from models.finding import Finding
        for f in data.get("findings", []):
            db.add(Finding(
                id=new_id(f["id"]),
                engagement_id=eng_new_id,
                title=f["title"],
                category=f.get("category"),
                description=f.get("description", ""),
                severity=f.get("severity", "MEDIUM"),
                status=f.get("status", "OPEN"),
                cvss_score=f.get("cvss_score"),
                cvss_vector=f.get("cvss_vector"),
                impact=f.get("impact"),
                technical_details=f.get("technical_details"),
                steps_to_reproduce=f.get("steps_to_reproduce"),
                mitigations=f.get("mitigations"),
                references=f.get("references"),
                created_by=resolve_user(f.get("created_by")),
                updated_by=resolve_user(f.get("updated_by")),
                created_at=parse_dt(f.get("created_at")) or datetime.utcnow(),
            ))
        await db.flush()

        # ── 5. TestCases (handle parent_id self-ref) ─────────────────
        from models.testcase import TestCase
        # First pass: pre-generate IDs
        all_tcs = data.get("testcases", [])
        for tc in all_tcs:
            new_id(tc["id"])

        # Topological insert: parents before children to satisfy self-ref FK
        inserted_ids: set[str] = set()
        remaining = list(all_tcs)
        while remaining:
            batch = []
            still_remaining = []
            for tc in remaining:
                old_parent = tc.get("parent_id")
                if not old_parent or old_parent in inserted_ids:
                    batch.append(tc)
                else:
                    still_remaining.append(tc)

            if not batch:
                # Prevent infinite loop: insert remaining with parent_id=None
                for tc in still_remaining:
                    tc["parent_id"] = None
                batch = still_remaining
                still_remaining = []

            for tc in batch:
                tc_new_id = remap(tc["id"])
                db.add(TestCase(
                    id=tc_new_id,
                    engagement_id=eng_new_id,
                    parent_id=remap(tc.get("parent_id")),
                    title=tc["title"],
                    category=tc.get("category", "Other"),
                    description=tc.get("description", ""),
                    steps=tc.get("steps"),
                    expected_result=tc.get("expected_result"),
                    actual_result=tc.get("actual_result"),
                    is_executed=tc.get("is_executed", False),
                    is_successful=tc.get("is_successful"),
                    notes=tc.get("notes"),
                    created_by=resolve_user(tc.get("created_by")),
                    updated_by=resolve_user(tc.get("updated_by")),
                    created_at=parse_dt(tc.get("created_at")) or datetime.utcnow(),
                ))
                inserted_ids.add(tc["id"])
            await db.flush()
            remaining = still_remaining

        # ── 6. Association tables ────────────────────────────────────
        from models.associations import (
            FindingAsset, FindingTestCase, FindingTag, TestCaseTag, TestCaseAsset,
            VaultItemFinding, VaultItemTestCase,
            CleanupArtifactFinding, CleanupArtifactTestCase, CleanupArtifactAsset,
            NoteAsset, NoteTestCase, NoteFinding, NoteVaultItem, NoteCleanupArtifact,
        )

        for fa in data.get("finding_assets", []):
            db.add(FindingAsset(
                finding_id=remap(fa["finding_id"]),
                asset_id=remap(fa["asset_id"]),
                port_ids=fa.get("port_ids"),
                remediated=fa.get("remediated", False),
                remediated_at=parse_dt(fa.get("remediated_at")),
            ))

        for ft in data.get("finding_testcases", []):
            db.add(FindingTestCase(
                finding_id=remap(ft["finding_id"]),
                testcase_id=remap(ft["testcase_id"]),
            ))

        for ftg in data.get("finding_tags", []):
            db.add(FindingTag(
                finding_id=remap(ftg["finding_id"]),
                tag_id=remap(ftg["tag_id"]),
            ))

        for tct in data.get("testcase_tags", []):
            db.add(TestCaseTag(
                testcase_id=remap(tct["testcase_id"]),
                tag_id=remap(tct["tag_id"]),
            ))

        for tca in data.get("testcase_assets", []):
            db.add(TestCaseAsset(
                testcase_id=remap(tca["testcase_id"]),
                asset_id=remap(tca["asset_id"]),
                port_ids=tca.get("port_ids"),
            ))
        await db.flush()

        # ── 7. Evidence (+ upload files) ─────────────────────────────
        from models.evidence import Evidence
        for ev in data.get("evidence", []):
            old_path = ev.get("file_path", "")
            ext = os.path.splitext(old_path)[1] if old_path else ""
            new_storage_name = f"{uuid.uuid4()}{ext}"

            # Upload file from ZIP to MinIO
            zip_path = f"attachments/{old_path}"
            if old_path and zip_path in zf.namelist():
                file_bytes = zf.read(zip_path)
                try:
                    await storage_service.upload_file(file_bytes, new_storage_name, content_type=ev.get("mime_type"))
                except Exception:
                    new_storage_name = old_path  # fallback

            db.add(Evidence(
                id=new_id(ev["id"]),
                finding_id=remap(ev.get("finding_id")),
                testcase_id=remap(ev.get("testcase_id")),
                engagement_id=eng_new_id,
                filename=new_storage_name,
                original_filename=ev.get("original_filename", "unknown"),
                file_path=new_storage_name,
                file_size=ev.get("file_size", 0),
                mime_type=ev.get("mime_type"),
                description=ev.get("description"),
                include_in_report=ev.get("include_in_report", True),
                created_by=resolve_user(ev.get("created_by")),
                updated_by=resolve_user(ev.get("updated_by")),
                created_at=parse_dt(ev.get("created_at")) or datetime.utcnow(),
            ))
        await db.flush()

        # ── 8. Vault Items (+ upload files) ──────────────────────────
        from models.vault import VaultItem
        for vi in data.get("vault_items", []):
            old_path = vi.get("file_path", "")
            new_vault_path = None
            if old_path:
                ext = os.path.splitext(old_path)[1] if old_path else ""
                new_vault_path = f"{uuid.uuid4()}{ext}"
                zip_path = f"attachments/{old_path}"
                if zip_path in zf.namelist():
                    file_bytes = zf.read(zip_path)
                    try:
                        await storage_service.upload_file(file_bytes, new_vault_path, content_type=None)
                    except Exception:
                        new_vault_path = old_path

            db.add(VaultItem(
                id=new_id(vi["id"]),
                engagement_id=eng_new_id,
                name=vi["name"],
                item_type=vi.get("item_type", "Note"),
                username=vi.get("username"),
                password=vi.get("password"),
                note=vi.get("note"),
                file_path=new_vault_path,
                filename=vi.get("filename"),
                description=vi.get("description"),
                created_by=resolve_user(vi.get("created_by")),
                updated_by=resolve_user(vi.get("updated_by")),
                created_at=parse_dt(vi.get("created_at")) or datetime.utcnow(),
            ))
        await db.flush()

        # Vault M2M
        for vif in data.get("vault_item_findings", []):
            db.add(VaultItemFinding(
                vault_item_id=remap(vif["vault_item_id"]),
                finding_id=remap(vif["finding_id"]),
            ))
        for vitc in data.get("vault_item_testcases", []):
            db.add(VaultItemTestCase(
                vault_item_id=remap(vitc["vault_item_id"]),
                testcase_id=remap(vitc["testcase_id"]),
            ))
        await db.flush()

        # ── 9. Cleanup Artifacts ─────────────────────────────────────
        from models.cleanup_artifact import CleanupArtifact
        for ca in data.get("cleanup_artifacts", []):
            db.add(CleanupArtifact(
                id=new_id(ca["id"]),
                engagement_id=eng_new_id,
                title=ca["title"],
                artifact_type=ca.get("artifact_type", "Other"),
                status=ca.get("status", "PENDING"),
                location=ca.get("location"),
                description=ca.get("description"),
                cleanup_notes=ca.get("cleanup_notes"),
                cleaned_at=parse_dt(ca.get("cleaned_at")),
                cleaned_by=resolve_user(ca.get("cleaned_by")) if ca.get("cleaned_by") else None,
                created_by=resolve_user(ca.get("created_by")),
                updated_by=resolve_user(ca.get("updated_by")),
                created_at=parse_dt(ca.get("created_at")) or datetime.utcnow(),
            ))
        await db.flush()

        # Cleanup M2M
        for caf in data.get("cleanup_artifact_findings", []):
            db.add(CleanupArtifactFinding(
                cleanup_artifact_id=remap(caf["cleanup_artifact_id"]),
                finding_id=remap(caf["finding_id"]),
            ))
        for catc in data.get("cleanup_artifact_testcases", []):
            db.add(CleanupArtifactTestCase(
                cleanup_artifact_id=remap(catc["cleanup_artifact_id"]),
                testcase_id=remap(catc["testcase_id"]),
            ))
        for caas in data.get("cleanup_artifact_assets", []):
            db.add(CleanupArtifactAsset(
                cleanup_artifact_id=remap(caas["cleanup_artifact_id"]),
                asset_id=remap(caas["asset_id"]),
            ))
        await db.flush()

        # ── 10. Notes ────────────────────────────────────────────────
        from models.note import Note
        for n in data.get("notes", []):
            db.add(Note(
                id=new_id(n["id"]),
                engagement_id=eng_new_id,
                title=n["title"],
                content=n.get("content", ""),
                created_by=resolve_user(n.get("created_by")),
                updated_by=resolve_user(n.get("updated_by")),
                created_at=parse_dt(n.get("created_at")) or datetime.utcnow(),
            ))
        await db.flush()

        # Note M2M
        for nf in data.get("note_findings", []):
            db.add(NoteFinding(note_id=remap(nf["note_id"]), finding_id=remap(nf["finding_id"])))
        for ntc in data.get("note_testcases", []):
            db.add(NoteTestCase(note_id=remap(ntc["note_id"]), testcase_id=remap(ntc["testcase_id"])))
        for na in data.get("note_assets", []):
            db.add(NoteAsset(note_id=remap(na["note_id"]), asset_id=remap(na["asset_id"])))
        for nvi in data.get("note_vault_items", []):
            db.add(NoteVaultItem(note_id=remap(nvi["note_id"]), vault_item_id=remap(nvi["vault_item_id"])))
        for nca in data.get("note_cleanup_artifacts", []):
            db.add(NoteCleanupArtifact(note_id=remap(nca["note_id"]), cleanup_artifact_id=remap(nca["cleanup_artifact_id"])))
        await db.flush()

        # ── 11. Threads & Comments ───────────────────────────────────
        from models.discussion import Thread, Comment
        for th in data.get("threads", []):
            # Remap resource_id if it was an engagement-scoped entity
            resource_id = remap(th.get("resource_id"))
            db.add(Thread(
                id=new_id(th["id"]),
                engagement_id=eng_new_id,
                resource_type=th.get("resource_type", "engagement"),
                resource_id=resource_id,
                title=th.get("title", ""),
                is_resolved=th.get("is_resolved", False),
                created_by=resolve_user(th.get("created_by")),
                created_at=parse_dt(th.get("created_at")) or datetime.utcnow(),
            ))
        await db.flush()

        for c in data.get("comments", []):
            thread_id = remap(c["thread_id"])
            if thread_id is None:
                continue
            db.add(Comment(
                id=new_id(c["id"]),
                thread_id=thread_id,
                content=c.get("content", ""),
                is_resolvable=c.get("is_resolvable", False),
                is_resolved=c.get("is_resolved", False),
                resolved_at=parse_dt(c.get("resolved_at")),
                resolved_by=resolve_user(c.get("resolved_by")) if c.get("resolved_by") else None,
                created_by=resolve_user(c.get("created_by")),
                created_at=parse_dt(c.get("created_at")) or datetime.utcnow(),
            ))
        await db.flush()

        # ── 12. Activity Logs ────────────────────────────────────────
        from models.discussion import ActivityLog
        for al in data.get("activity_logs", []):
            db.add(ActivityLog(
                id=new_id(al["id"]),
                engagement_id=eng_new_id,
                user_id=resolve_user(al.get("user_id")),
                action=al.get("action", "imported"),
                resource_type=al.get("resource_type", "engagement"),
                resource_id=remap(al.get("resource_id")) or eng_new_id,
                resource_name=al.get("resource_name"),
                details=al.get("details"),
                created_at=parse_dt(al.get("created_at")) or datetime.utcnow(),
            ))
        await db.flush()

        # ── 13. Attacker Nodes & Edges ───────────────────────────────
        from models.attacker_node import AttackerNode, AttackerNodeEdge
        for an in data.get("attacker_nodes", []):
            db.add(AttackerNode(
                id=new_id(an["id"]),
                engagement_id=eng_new_id,
                name=an.get("name", "Threat Actor"),
                point_of_presence=an.get("point_of_presence", "External"),
                description=an.get("description"),
                created_at=parse_dt(an.get("created_at")) or datetime.utcnow(),
            ))
        await db.flush()

        for edge in data.get("attacker_node_edges", []):
            attacker_node_id = remap(edge["attacker_node_id"])
            if attacker_node_id is None:
                continue
            db.add(AttackerNodeEdge(
                id=new_id(edge["id"]),
                attacker_node_id=attacker_node_id,
                target_node_id=remap(edge.get("target_node_id")) or "",
                target_node_type=edge.get("target_node_type", ""),
            ))
        await db.flush()

        # ── 14. Attack Graph Layout ──────────────────────────────────
        agl_data = data.get("attack_graph_layout")
        if agl_data:
            from models.attack_graph_layout import AttackGraphLayout
            # Remap positions JSON keys
            positions_raw = agl_data.get("positions", "{}")
            try:
                positions = json.loads(positions_raw) if isinstance(positions_raw, str) else positions_raw
                remapped_pos = {}
                for key, value in positions.items():
                    remapped_pos[remap(key) or key] = value
                positions_str = json.dumps(remapped_pos)
            except Exception:
                positions_str = positions_raw if isinstance(positions_raw, str) else json.dumps(positions_raw)

            db.add(AttackGraphLayout(
                id=new_id(agl_data["id"]),
                engagement_id=eng_new_id,
                positions=positions_str,
                pinned_by=current_user.id,
                pinned_at=parse_dt(agl_data.get("pinned_at")) or datetime.utcnow(),
            ))
            await db.flush()

        # ── 15. Report Layouts ───────────────────────────────────────
        from models.report_layout import ReportLayout, ReportSection
        for rl in data.get("report_layouts", []):
            rl_new_id = new_id(rl["id"])
            db.add(ReportLayout(
                id=rl_new_id,
                name=rl.get("name", "Default"),
                engagement_id=eng_new_id,
                is_default=rl.get("is_default", False),
                created_by=resolve_user(rl.get("created_by")),
                created_at=parse_dt(rl.get("created_at")) or datetime.utcnow(),
            ))
            await db.flush()
            for sec in rl.get("sections", []):
                db.add(ReportSection(
                    id=new_id(sec["id"]),
                    report_layout_id=rl_new_id,
                    section_type=sec.get("section_type", "text"),
                    title=sec.get("title", ""),
                    content=sec.get("content", ""),
                    sort_order=sec.get("sort_order", 0),
                ))
            await db.flush()

        # ── Log import activity ──────────────────────────────────────
        from models.discussion import ActivityLog
        db.add(ActivityLog(
            id=str(uuid.uuid4()),
            engagement_id=eng_new_id,
            user_id=current_user.id,
            action="imported_engagement",
            resource_type="engagement",
            resource_id=eng_new_id,
            resource_name=new_eng.name,
            details=f"Imported from archive: {file.filename}",
            created_at=datetime.utcnow(),
        ))

        await db.commit()
        zf.close()

        return {
            "id": eng_new_id,
            "name": new_eng.name,
            "message": "Engagement imported successfully",
        }

    except Exception as e:
        await db.rollback()
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Import failed: {str(e)}"
        )
