"""
Engagement Export / Import
--------------------------
GET  /engagements/{id}/export  →  ZIP download
POST /engagements/import       →  ZIP upload → new engagement
"""

from fastapi import APIRouter, Depends, HTTPException, Header, Request, UploadFile, File, Form, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from database import get_db
from auth.dependencies import get_current_user
from models.user import User, UserRole
from utils.storage import storage_service
from utils.uploads import read_upload_capped
# Note: vault secret columns are encrypted at rest via the EncryptedText
# column type — reads come back as plaintext, writes encrypt on bind.
# Export and import paths therefore pass plain str values; no per-call
# encrypt_field / decrypt_field wrapping required.

import hashlib
import io
import json
import logging
import os
import traceback
import uuid
import zipfile
from datetime import datetime
from typing import Optional

import pyzipper

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/engagements", tags=["engagements"])


# GHSA-f826-6226-4rfw: bound the receive side and reject zip bombs by
# compression ratio. The archive byte cap protects memory/network budget
# on ingest; the ratio cap is the actual bomb detector (legitimate JSON
# exports rarely top 30:1, zip bombs hit 1000:1+). Both are env-tunable.
IMPORT_MAX_ARCHIVE_BYTES = int(
    os.getenv("ENGAGEMENT_IMPORT_MAX_ARCHIVE_BYTES", str(200 * 1024 * 1024))
)
IMPORT_MAX_COMPRESSION_RATIO = int(
    os.getenv("ENGAGEMENT_IMPORT_MAX_COMPRESSION_RATIO", "100")
)

# Optional AES-encrypted-archive support (GHSA-3r7j-7h5r-gxgx follow-up).
# When the operator supplies a passphrase via the X-Export-Passphrase
# header on export — or X-Import-Passphrase on import / import preview —
# the archive is wrapped in pyzipper's AES-256 (WinZip AES extension).
# Server never persists the passphrase; it is a one-shot wrap.
MIN_EXPORT_PASSPHRASE_LEN = 16

# GHSA-vwgf-r8qp-8gwr (CWE-353): manifest content-hash bound to every
# archive member. Version 1.2 exports carry a SHA-256 per file plus a
# root digest over the sorted map; import verifies every entry and
# rejects any mismatch. Legacy 1.0/1.1 archives have no digest — imports
# refuse them by default so a forged v1.1-labelled archive can't
# downgrade past the check. Operators with pre-1.2 archives that
# genuinely need re-importing can set the env var below to False for
# one-shot use.
MANIFEST_VERSION = "1.2"
IMPORT_REQUIRE_DIGEST = os.getenv(
    "ENGAGEMENT_IMPORT_REQUIRE_DIGEST", "true"
).lower() not in ("false", "0", "no")


def _validate_passphrase(passphrase: Optional[str], *, kind: str) -> Optional[str]:
    """Length-validate a passphrase coming off an export/import header.

    Returns the passphrase verbatim when non-empty, ``None`` when absent.
    Refuses too-short input up front rather than producing an archive
    that nobody can decrypt later, or accepting one with weak protection.
    """
    if not passphrase:
        return None
    if len(passphrase) < MIN_EXPORT_PASSPHRASE_LEN:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{kind.capitalize()} passphrase must be at least "
                f"{MIN_EXPORT_PASSPHRASE_LEN} characters."
            ),
        )
    return passphrase


def _zip_is_aes_encrypted(zf: zipfile.ZipFile) -> bool:
    """True when any central-directory entry has the encrypted flag set.

    We only ever produce all-or-nothing archives (every entry encrypted
    or none), but scanning the whole central directory keeps us honest
    against hand-crafted hybrid archives an attacker might upload — any
    hint of encryption demands the passphrase path.
    """
    for info in zf.infolist():
        if info.flag_bits & 0x1:
            return True
    return False


def _open_engagement_archive(content: bytes, passphrase: Optional[str]) -> zipfile.ZipFile:
    """Return a read-ready ZipFile (or pyzipper AESZipFile) for the
    uploaded engagement archive bytes. Caller uses the result
    transparently — both expose ``namelist`` / ``read`` / ``infolist``.

    Raises HTTPException(400) on:
      - malformed ZIP container
      - encrypted archive with no passphrase supplied
      - encrypted archive with the wrong passphrase
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Invalid ZIP file")
    if not _zip_is_aes_encrypted(zf):
        return zf
    zf.close()
    if not passphrase:
        raise HTTPException(
            status_code=400,
            detail="Archive is encrypted — supply the import passphrase to decrypt.",
        )
    azf = pyzipper.AESZipFile(io.BytesIO(content))
    azf.setpassword(passphrase.encode("utf-8"))
    # Probe the smallest non-empty entry so a wrong passphrase fails
    # here with a clear 400 instead of mid-import.
    try:
        for info in azf.infolist():
            if info.file_size > 0:
                azf.read(info.filename)
                break
    except RuntimeError as exc:
        azf.close()
        raise HTTPException(
            status_code=400,
            detail="Could not decrypt archive — check the import passphrase.",
        ) from exc
    return azf


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _compute_root_digest(digests: dict[str, str]) -> str:
    """SHA-256 over the sorted ``name\\thex\\n`` lines of the per-file
    digest map. Deterministic — sorting the map means two archives with
    the same content but different member-write order produce the same
    root digest. This is what the manifest's ``root_digest`` field
    carries and what the preview modal displays to the operator for
    out-of-band verification.
    """
    payload = "".join(f"{name}\t{digest}\n" for name, digest in sorted(digests.items()))
    return _sha256_hex(payload.encode("utf-8"))


def _verify_archive_digests(zf: zipfile.ZipFile, manifest: dict) -> None:
    """GHSA-vwgf-r8qp-8gwr: recompute the SHA-256 of every archive
    member listed in the manifest's ``digests`` map and refuse the
    import if any digest is missing, unexpected, or mismatches the
    stored value. Also refuses when the manifest has no ``digests``
    field at all (legacy pre-1.2 archive) unless the operator has
    opted into legacy behaviour via ``ENGAGEMENT_IMPORT_REQUIRE_DIGEST=false``.

    The check is bind-to-content, not bind-to-metadata: we read each
    member out of the ZIP and hash the bytes rather than trusting
    ``ZipInfo.CRC``. A hand-crafted archive that ships a valid digest
    map alongside tampered content still gets caught because the
    recomputed hash won't match.
    """
    digests = manifest.get("digests")
    # Strict shape validation: every key a non-empty str, every value a
    # 64-char lower-hex digest. An attacker who ships a valid-looking
    # manifest with bogus digest shapes (list values, uppercase hex,
    # truncated hashes) shouldn't drop through with a confusing
    # mismatch error; refuse the archive outright.
    if isinstance(digests, dict):
        for name, digest in digests.items():
            if not isinstance(name, str) or not name:
                raise HTTPException(
                    status_code=400,
                    detail="Archive manifest.digests contains a non-string key.",
                )
            if (
                not isinstance(digest, str)
                or len(digest) != 64
                or not all(c in "0123456789abcdef" for c in digest)
            ):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Archive manifest.digests['{name}'] is not a valid "
                        "64-char lower-hex SHA-256 digest."
                    ),
                )
    if not isinstance(digests, dict) or not digests:
        if IMPORT_REQUIRE_DIGEST:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Archive is missing manifest.digests (pre-1.2 export). "
                    "Refusing import — set ENGAGEMENT_IMPORT_REQUIRE_DIGEST=false "
                    "on the backend to accept legacy archives, or re-export "
                    "the source engagement from a current RedWire instance."
                ),
            )
        logger.warning(
            "Engagement import: archive %s carries no digest map (version=%s). "
            "Integrity check skipped per ENGAGEMENT_IMPORT_REQUIRE_DIGEST=false.",
            manifest.get("engagement_name"), manifest.get("version"),
        )
        return

    # Every named member must exist. Extras are permitted (they're
    # ignored on import anyway) but every declared digest MUST resolve
    # to a present-and-matching file. This ordering is the important
    # one — a tampered archive that adds extras alongside a valid
    # digest map is caught by the size/ratio caps and by the fact
    # that the extras don't participate in the import.
    namelist = set(zf.namelist())
    for name, expected in digests.items():
        if name not in namelist:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Archive integrity check failed: manifest lists "
                    f"'{name}' but the file is missing from the archive."
                ),
            )
        actual = _sha256_hex(zf.read(name))
        if not isinstance(expected, str) or actual != expected:
            logger.warning(
                "Engagement import: digest mismatch on %r (expected=%s actual=%s)",
                name, expected, actual,
            )
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Archive integrity check failed: '{name}' does not "
                    f"match the digest recorded in the manifest. The archive "
                    f"has been tampered with, corrupted in transit, or is "
                    f"not a genuine RedWire export."
                ),
            )

    # Also verify the root digest — the digest map itself could have
    # been tampered with by an attacker who recomputed the per-file
    # entries. The root is a self-check that pins the map's shape,
    # not just the values.
    expected_root = manifest.get("root_digest")
    computed_root = _compute_root_digest(digests)
    if expected_root and expected_root != computed_root:
        raise HTTPException(
            status_code=400,
            detail=(
                "Archive integrity check failed: manifest root_digest does "
                "not match the recomputed digest of the digest map. Refusing."
            ),
        )


def _reject_zip_bomb(zf: zipfile.ZipFile) -> None:
    """Walk the archive's central directory and refuse members whose
    declared compression ratio looks like a zip bomb. Cheap — central
    directory only, no inflate runs here.
    """
    for info in zf.infolist():
        if info.compress_size == 0:
            # Directory entries or zero-byte members. Skip.
            continue
        ratio = info.file_size / info.compress_size
        if ratio > IMPORT_MAX_COMPRESSION_RATIO:
            logger.warning(
                "Refused engagement-import archive: member %r ratio %.0f:1 > %d:1 cap",
                info.filename, ratio, IMPORT_MAX_COMPRESSION_RATIO,
            )
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Archive member '{info.filename}' has a suspicious "
                    f"compression ratio of {ratio:.0f}:1 (limit "
                    f"{IMPORT_MAX_COMPRESSION_RATIO}:1). Refusing as a potential "
                    "zip bomb."
                ),
            )

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

@router.get("/{engagement_id}/export/preview")
async def export_engagement_preview(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cheap probe used by the export modal to decide whether to surface
    the plaintext-secret warning + acknowledgement before triggering the
    real export. Returns the same flag the manifest will carry so the UI
    and the archive can't disagree.
    """
    if current_user.role not in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]:
        raise HTTPException(status_code=403, detail="Admin or Team Lead role required")

    from models.engagement import Engagement
    from models.vault import VaultItem

    eng_res = await db.execute(select(Engagement.id).where(Engagement.id == engagement_id))
    if eng_res.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Engagement not found")

    vi_res = await db.execute(
        select(VaultItem).where(VaultItem.engagement_id == engagement_id)
    )
    vault_items = vi_res.scalars().all()
    contains = any(
        (vi.username or vi.password or vi.note or vi.file_path) for vi in vault_items
    )
    return {
        "vault_item_count": len(vault_items),
        "contains_plaintext_secrets": contains,
    }


@router.get("/{engagement_id}/export")
async def export_engagement(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    x_export_passphrase: Optional[str] = Header(default=None, alias="X-Export-Passphrase"),
):
    """Export an engagement as a ZIP archive with all data and attachments.

    When ``X-Export-Passphrase`` is supplied the resulting archive is
    AES-256 encrypted via pyzipper (WinZip AES extension). The server
    never persists the passphrase; the operator hands it off out-of-band.
    Filename gains a ``.enc.zip`` suffix as a UX cue and so the import
    flow has a hint to prompt for a passphrase before upload.
    """
    if current_user.role not in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]:
        raise HTTPException(status_code=403, detail="Admin or Team Lead role required")

    passphrase = _validate_passphrase(x_export_passphrase, kind="export")

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
    # GHSA-3r7j-7h5r-gxgx: decrypt the Fernet-protected vault columns
    # before serialising so the archive carries plaintext that the
    # destination instance can re-encrypt under ITS key on import.
    # Shipping this-instance ciphertext would be useless on any other
    # instance (different VAULT_ENCRYPTION_KEY). The archive is loudly
    # flagged as containing plaintext secrets via SECURITY_WARNING.txt
    # and the manifest below.
    # EncryptedText decrypts on ORM read, so _row_dict already pulls
    # plaintext for username / password / note. No per-export decrypt
    # wrap needed.
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

    # ── attack graph layouts ─────────────────────────────────────────
    # 1:N — `is_active` flags the currently-selected layout, but an
    # engagement can carry multiple named layouts. Export them all so the
    # destination instance reconstructs the full picker, not just the
    # active one. Old export archives carry `attack_graph_layout` as a
    # single object; import handles both shapes for backward-compat.
    from models.attack_graph_layout import AttackGraphLayout
    agl_res = await db.execute(
        select(AttackGraphLayout).where(AttackGraphLayout.engagement_id == engagement_id)
    )
    data["attack_graph_layouts"] = [
        _row_dict(agl, ["id", "name", "is_active", "positions", "pinned_at"])
        for agl in agl_res.scalars().all()
    ]

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
    if passphrase:
        zf_ctx = pyzipper.AESZipFile(
            zip_buf, 'w', compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES,
        )
        zf_ctx.setpassword(passphrase.encode("utf-8"))
    else:
        zf_ctx = zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED)
    with zf_ctx as zf:
        # GHSA-vwgf-r8qp-8gwr: build every member's bytes in memory
        # first so we can compute a SHA-256 for each before writing the
        # manifest. The manifest carries the digest map and a root
        # digest over the sorted map; on import, verification catches
        # any tampering-in-transit or storage corruption. Fabricated
        # archives are handled by the manifest-content hardening
        # follow-up (users[] auto-map, evidence path prefix-check,
        # decompression caps) — the digest layer here is specifically
        # bind-content-to-manifest.
        _has_vault_secrets = any(
            (vi.username or vi.password or vi.note or vi.file_path)
            for vi in vault_items
        )

        members: dict[str, bytes] = {}

        # GHSA-3r7j-7h5r-gxgx: human-readable banner so anyone who
        # touches this archive (curl, scp, backup, share-drive viewer)
        # sees the plaintext warning even without opening manifest.json.
        if _has_vault_secrets:
            members["SECURITY_WARNING.txt"] = (
                "================================================================\n"
                "  REDWIRE EXPORT — CONTAINS PLAINTEXT SECRETS\n"
                "================================================================\n"
                "\n"
                "This archive contains plaintext credentials and/or vault file\n"
                "attachments from an engagement (vault item username/password/\n"
                "note columns and any uploaded FILE-type vault attachments).\n"
                "\n"
                "Vault encryption-at-rest is intentionally stripped on export so\n"
                "the destination RedWire instance can re-encrypt under its own\n"
                "key on import. Until that import completes, treat this archive\n"
                "like a password file:\n"
                "\n"
                "  - do NOT email, post to Slack/Teams, or upload to cloud\n"
                "    storage that is not under RedWire's control;\n"
                "  - hand off via encrypted channel (signed PGP, encrypted\n"
                "    USB, S3 SSE bucket with restricted IAM, etc.);\n"
                "  - delete the local copy immediately after the destination\n"
                "    instance has imported it.\n"
                "\n"
                "manifest.json -> contains_plaintext_secrets: true\n"
                "================================================================\n"
            ).encode("utf-8")

        # engagement.json — deterministic serialization so the same
        # export produces the same bytes (matters for the digest).
        members["engagement.json"] = json.dumps(
            data, indent=2, default=str, sort_keys=True
        ).encode("utf-8")

        # attachments — evidence files
        for ev in evidence_list:
            if ev.file_path:
                try:
                    file_bytes = await storage_service.download_file(ev.file_path)
                    if file_bytes is None:
                        continue
                    members[f"attachments/{ev.file_path}"] = file_bytes
                except Exception:
                    pass  # skip missing files

        # attachments — vault files
        # GHSA-3r7j-7h5r-gxgx Issue 3 follow-up: MinIO blob may be
        # Fernet ciphertext (vault items uploaded post-RDW-057) or
        # legacy plaintext. Always run through decrypt_bytes — it
        # passes plaintext through untouched and decrypts ciphertext.
        # The export ZIP must carry plaintext to match the existing
        # "exports ship plaintext with a banner" semantics for the
        # vault secret fields (username / password / note); shipping
        # ciphertext would force the importing instance to share our
        # VAULT_ENCRYPTION_KEY, which is the opposite of the design.
        from utils.vault_crypto import decrypt_bytes as _decrypt_vault_bytes
        for vi in vault_items:
            if vi.file_path:
                try:
                    file_bytes = await storage_service.download_file(vi.file_path)
                    if file_bytes is None:
                        continue
                    file_bytes = _decrypt_vault_bytes(file_bytes)
                    members[f"attachments/{vi.file_path}"] = file_bytes
                except Exception:
                    pass

        # Digests + manifest. Sort names so the map is
        # ordering-independent (JSON serialisation preserves insertion
        # order, which would otherwise let two identical exports differ
        # on disk).
        digests = {name: _sha256_hex(members[name]) for name in sorted(members)}
        root_digest = _compute_root_digest(digests)

        manifest = {
            "version": MANIFEST_VERSION,
            "exported_at": datetime.utcnow().isoformat(),
            "engagement_name": eng.name,
            "source": "redwire",
            "contains_plaintext_secrets": _has_vault_secrets,
            "digests": digests,
            "root_digest": root_digest,
        }
        zf.writestr(
            "manifest.json",
            json.dumps(manifest, indent=2, sort_keys=True),
        )
        for name in sorted(members):
            zf.writestr(name, members[name])

    zip_buf.seek(0)
    safe_name = eng.name.replace(" ", "_").replace("/", "-")[:50]
    _suffix = "enc.zip" if passphrase else "zip"
    filename = f"redwire_export_{safe_name}_{datetime.utcnow().strftime('%Y%m%d')}.{_suffix}"

    # GHSA-3r7j-7h5r-gxgx: audit-log every export, flagging when it
    # carries plaintext vault material so the engagement's activity
    # feed records who pulled secrets and when.
    from utils.collaboration import create_activity_log
    _action = "exported_engagement_with_secrets" if _has_vault_secrets else "exported_engagement"
    _enc_note = " (AES-encrypted)" if passphrase else ""
    _details = (
        f"Exported engagement archive{_enc_note} (contains plaintext vault secrets): {filename}"
        if _has_vault_secrets
        else f"Exported engagement archive{_enc_note}: {filename}"
    )
    await create_activity_log(
        db=db,
        engagement_id=engagement_id,
        user_id=current_user.id,
        action=_action,
        resource_type="engagement",
        resource_id=engagement_id,
        resource_name=eng.name,
        details=_details,
    )

    return StreamingResponse(
        zip_buf,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            # GHSA-vwgf-r8qp-8gwr: surface the archive's root SHA-256
            # to the export UI so the operator can send it out-of-band
            # to whoever will import the archive.
            "X-Archive-Root-Digest": root_digest,
        },
    )

# ═════════════════════════════════════════════════════════════════════════
#  IMPORT PREVIEW — identify unmatched users before importing
# ═════════════════════════════════════════════════════════════════════════

@router.post("/import/preview")
async def preview_import(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    x_import_passphrase: Optional[str] = Header(default=None, alias="X-Import-Passphrase"),
):
    """Preview a ZIP archive: return matched & unmatched users so the admin can map them."""
    # GHSA-f826-6226-4rfw: READ_ONLY_ADMIN dropped — import is a write path
    # and a read-only role should never be able to trigger DB ingestion.
    if current_user.role not in [UserRole.ADMIN, UserRole.TEAM_LEAD]:
        raise HTTPException(status_code=403, detail="Admin or Team Lead role required")

    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="File must be a .zip archive")

    passphrase = _validate_passphrase(x_import_passphrase, kind="import")
    content = await read_upload_capped(
        file, IMPORT_MAX_ARCHIVE_BYTES,
        detail=f"Engagement-import archive exceeds the {IMPORT_MAX_ARCHIVE_BYTES}-byte size limit.",
    )
    zf = _open_engagement_archive(content, passphrase)
    _reject_zip_bomb(zf)

    if "manifest.json" not in zf.namelist():
        raise HTTPException(status_code=400, detail="Missing manifest.json in archive")
    manifest = json.loads(zf.read("manifest.json"))
    if manifest.get("source") != "redwire":
        raise HTTPException(status_code=400, detail="Archive is not a RedWire export")

    # GHSA-vwgf-r8qp-8gwr: verify every archive member against its
    # manifest-recorded SHA-256 BEFORE any further parsing so a
    # tampered engagement.json never reaches the ORM layer.
    _verify_archive_digests(zf, manifest)

    if "engagement.json" not in zf.namelist():
        raise HTTPException(status_code=400, detail="Missing engagement.json in archive")
    data = json.loads(zf.read("engagement.json"))
    zf.close()

    exported_users: dict = data.get("users", {})
    engagement_payload = data.get("engagement", {}) or {}
    engagement_name = engagement_payload.get("name", "Unknown")

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

    # Surface a content summary to the operator BEFORE the import fires —
    # the archive may have been built weeks ago, renamed, or handed over
    # blind. Counts come straight off the bundled lists so they reflect
    # exactly what the import endpoint will create, including any 1:N
    # tables (findings, evidence, etc.).
    def _len(key: str) -> int:
        v = data.get(key)
        return len(v) if isinstance(v, list) else 0

    counts = {
        "findings": _len("findings"),
        "assets": _len("assets"),
        "testcases": _len("testcases"),
        "evidence": _len("evidence"),
        "vault_items": _len("vault_items"),
        "notes": _len("notes"),
        "cleanup_artifacts": _len("cleanup_artifacts"),
        "threads": _len("threads"),
        "attacker_nodes": _len("attacker_nodes"),
        "report_layouts": _len("report_layouts"),
    }

    return {
        "engagement_name": engagement_name,
        "engagement": {
            "name": engagement_name,
            "client_name": engagement_payload.get("client_name"),
            "engagement_type": engagement_payload.get("engagement_type"),
            "status": engagement_payload.get("status"),
            "start_date": engagement_payload.get("start_date"),
            "end_date": engagement_payload.get("end_date"),
            "description": engagement_payload.get("description"),
        },
        "archive": {
            "exported_at": manifest.get("exported_at"),
            "source_version": manifest.get("version"),
            "contains_plaintext_secrets": bool(manifest.get("contains_plaintext_secrets")),
            "root_digest": manifest.get("root_digest"),
        },
        "counts": counts,
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
    x_import_passphrase: Optional[str] = Header(default=None, alias="X-Import-Passphrase"),
):
    """Import an engagement from a ZIP archive. Accepts optional user_mapping JSON."""
    # GHSA-f826-6226-4rfw: READ_ONLY_ADMIN dropped — see preview_import note.
    if current_user.role not in [UserRole.ADMIN, UserRole.TEAM_LEAD]:
        raise HTTPException(status_code=403, detail="Admin or Team Lead role required")

    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="File must be a .zip archive")

    passphrase = _validate_passphrase(x_import_passphrase, kind="import")
    content = await read_upload_capped(
        file, IMPORT_MAX_ARCHIVE_BYTES,
        detail=f"Engagement-import archive exceeds the {IMPORT_MAX_ARCHIVE_BYTES}-byte size limit.",
    )
    zf = _open_engagement_archive(content, passphrase)
    _reject_zip_bomb(zf)

    # Read manifest
    if "manifest.json" not in zf.namelist():
        raise HTTPException(status_code=400, detail="Missing manifest.json in archive")
    manifest = json.loads(zf.read("manifest.json"))
    if manifest.get("source") != "redwire":
        raise HTTPException(status_code=400, detail="Archive is not a RedWire export")

    # GHSA-vwgf-r8qp-8gwr: verify every archive member against its
    # manifest-recorded SHA-256 BEFORE any further parsing so a
    # tampered engagement.json never reaches the ORM layer.
    _verify_archive_digests(zf, manifest)

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
                    # GHSA-rcjp-27mp-v69m: never fall back to the bundle-supplied
                    # path — that would persist an attacker-controlled storage
                    # key pointing at another engagement's object. Skip the row.
                    continue

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
                # GHSA-3r7j-7h5r-gxgx Issue 3 follow-up: force the .enc
                # suffix so the new blob has the same on-disk shape as
                # native uploads. Helps the operator visually distinguish
                # encrypted blobs from any legacy plaintext still in
                # MinIO (pre-RDW-057) and matches the .enc convention
                # in routers/vault.py::upload_vault_file.
                if not ext.endswith(".enc"):
                    ext = (ext or "") + ".enc"
                new_vault_path = f"vault/{uuid.uuid4()}{ext}"
                zip_path = f"attachments/{old_path}"
                if zip_path in zf.namelist():
                    file_bytes = zf.read(zip_path)
                    try:
                        # GHSA-3r7j-7h5r-gxgx Issue 3 follow-up: the export
                        # path decrypts before zipping, so the archive
                        # carries plaintext. Encrypt under THIS instance's
                        # VAULT_ENCRYPTION_KEY before persisting to MinIO.
                        # Without this, imported vault files would sit in
                        # the destination bucket as plaintext — the exact
                        # bug the at-rest fix exists to close.
                        from utils.vault_crypto import encrypt_bytes as _encrypt_vault_bytes
                        ciphertext = _encrypt_vault_bytes(file_bytes)
                        await storage_service.upload_file(
                            ciphertext,
                            new_vault_path,
                            content_type="application/octet-stream",
                        )
                    except Exception:
                        # GHSA-rcjp-27mp-v69m: drop the file reference rather
                        # than persisting the attacker-supplied path. VaultItem
                        # carries non-file payload too (username/password/note),
                        # so the row is still useful — vault.py:322 already
                        # handles file_path is None with a 404 on download.
                        new_vault_path = None

            # GHSA-3r7j-7h5r-gxgx: persist vault text columns under the
            # destination instance's Fernet key. The archive carries
            # plaintext (see export side); the EncryptedText column type
            # on VaultItem encrypts on bind, so we hand it the raw
            # plaintext from the archive and let the type layer do the
            # work. Same applies to the file blob above (encrypted via
            # encrypt_bytes before MinIO upload).
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
                # New row's blob just got encrypted above (if there was
                # one), so it's at the current scheme.
                encryption_version=1,
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
        from models.discussion import Thread, Comment, ResourceType
        # GHSA-7x2f-ff7r-h388 #8 (CWE-20): the Thread.resource_type
        # column is a plain String(50) (the model comment reads
        # "Changed from Enum to String") — no DB-level enum guard.
        # An archive whose `resource_type` value doesn't belong to the
        # ResourceType enum would land as legit-looking data and later
        # break every consumer that assumes the value is one of the
        # 12 documented shapes (serializer, /engagements/{id}/threads
        # UI grouping, discussions router's engagement scoping).
        # Coerce unknown values to ENGAGEMENT + log — the value's not
        # attacker-controlled in a way that lets them cross a trust
        # boundary, so silently normalising is preferable to refusing
        # the whole archive.
        _valid_resource_types = {v.value for v in ResourceType}
        for th in data.get("threads", []):
            # Remap resource_id if it was an engagement-scoped entity
            resource_id = remap(th.get("resource_id"))
            raw_rt = th.get("resource_type", "engagement")
            if raw_rt not in _valid_resource_types:
                logger.warning(
                    "engagement-import: thread %r has unknown resource_type=%r; "
                    "coercing to 'engagement'", th.get("id"), raw_rt,
                )
                raw_rt = ResourceType.ENGAGEMENT.value
            db.add(Thread(
                id=new_id(th["id"]),
                engagement_id=eng_new_id,
                resource_type=raw_rt,
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
        # GHSA-7x2f-ff7r-h388 #8 (CWE-20): ActivityLog.resource_type
        # is the same String(50) shape and lands from the same archive
        # section; same enum-coerce policy as threads above.
        for al in data.get("activity_logs", []):
            raw_rt = al.get("resource_type", "engagement")
            if raw_rt not in _valid_resource_types:
                logger.warning(
                    "engagement-import: activity_log %r has unknown resource_type=%r; "
                    "coercing to 'engagement'", al.get("id"), raw_rt,
                )
                raw_rt = ResourceType.ENGAGEMENT.value
            db.add(ActivityLog(
                id=new_id(al["id"]),
                engagement_id=eng_new_id,
                user_id=resolve_user(al.get("user_id")),
                action=al.get("action", "imported"),
                resource_type=raw_rt,
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

        # ── 14. Attack Graph Layouts ─────────────────────────────────
        # New archives ship a list (`attack_graph_layouts`); old archives
        # ship a single object (`attack_graph_layout`). Normalize to a
        # list and iterate so both shapes import cleanly.
        agl_list = data.get("attack_graph_layouts")
        if agl_list is None:
            single = data.get("attack_graph_layout")
            agl_list = [single] if single else []
        if agl_list:
            from models.attack_graph_layout import AttackGraphLayout
            for agl_data in agl_list:
                if not agl_data:
                    continue
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
                    name=agl_data.get("name") or "Default",
                    is_active=bool(agl_data.get("is_active", False)),
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
        # GHSA-vwgf-r8qp-8gwr: include the archive's manifest root
        # digest so forensic queries can tie an imported engagement
        # back to a specific archive without digging through server
        # logs. Truncated to 16 hex chars in the details string for
        # readability; the full digest is available in server logs
        # and by re-hashing the archive if it's still on hand.
        _archive_fp = (manifest.get("root_digest") or "unknown")[:16]
        from models.discussion import ActivityLog
        db.add(ActivityLog(
            id=str(uuid.uuid4()),
            engagement_id=eng_new_id,
            user_id=current_user.id,
            action="imported_engagement",
            resource_type="engagement",
            resource_id=eng_new_id,
            resource_name=new_eng.name,
            details=(
                f"Imported from archive: {file.filename} "
                f"(fingerprint {_archive_fp}…)"
            ),
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
