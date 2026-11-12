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
from auth.permissions import has_global_permission
from models.permission import Permission
from models.user import User, UserRole
from utils.storage import storage_service
from utils.uploads import read_upload_capped, content_disposition_attachment, safe_content_type, sanitize_original_filename
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
# 1.3: every model column is exported (field lists derived from the models),
# plus engagement tags/phases/skills, ATT&CK links, vault-asset and chain
# links, and finding reviews. Older archives still import.
MANIFEST_VERSION = "1.3"
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
                # Streamed read via the safe helper — a wrong passphrase
                # raises on the first inflater chunk (bytes needed for
                # decryption verification), same effect as read() but
                # bounded by the per-member cap. See _read_member_safely.
                _read_member_safely(azf, info.filename)
                break
    except RuntimeError as exc:
        azf.close()
        raise HTTPException(
            status_code=400,
            detail="Could not decrypt archive — check the import passphrase.",
        ) from exc
    return azf


def _read_member_safely(
    zf: zipfile.ZipFile, name: str, max_bytes: int = IMPORT_MAX_ARCHIVE_BYTES
) -> bytes:
    """Read a zip archive member with a hard per-member byte ceiling.

    GHSA-f826-6226-4rfw follow-up. The primary bomb guard
    (``_reject_zip_bomb``) computes ``file_size / compress_size`` from
    the central-directory metadata; a hand-crafted archive that
    under-declares ``file_size`` can slip past the ratio cap while
    still decompressing to gigabytes. This helper decompresses through
    ``zf.open(name)`` (streams from the inflater rather than trusting
    the declared size), tracks the running total, and raises 400 the
    moment we cross ``max_bytes``. Same behaviour for pyzipper's
    ``AESZipFile`` — its ``.open()`` returns a compatible stream.

    ``max_bytes`` defaults to ``IMPORT_MAX_ARCHIVE_BYTES`` — no single
    member can legitimately exceed the whole archive we agreed to
    accept.
    """
    buf = io.BytesIO()
    total = 0
    # 64 KiB chunks — inflater efficiency without unbounded RAM growth
    # for pathological input.
    with zf.open(name) as fp:
        while True:
            chunk = fp.read(65536)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                logger.warning(
                    "Engagement import: member %r exceeded per-member cap "
                    "(read %d bytes, cap %d) — refusing.",
                    name, total, max_bytes,
                )
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Archive member '{name}' exceeds the per-member "
                        f"size cap ({max_bytes} bytes). Refusing — possible "
                        f"zip bomb."
                    ),
                )
            buf.write(chunk)
    return buf.getvalue()


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
        actual = _sha256_hex(_read_member_safely(zf, name))
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


def _import_anchor(th: dict, resource_type: str) -> dict:
    """Thread anchor columns from an archive row, validated: kept only when the
    field is annotatable for the resource type and the quote is a string; the
    rest is clamped to the column sizes. Anything else imports as a plain
    (unanchored) thread rather than failing the whole archive."""
    from routers.discussions import _ANCHOR_FIELDS
    field, quote = th.get("anchor_field"), th.get("anchor_quote")
    if (not isinstance(field, str) or not isinstance(quote, str)
            or field not in _ANCHOR_FIELDS.get(resource_type, ())):
        return {}

    def _ctx(v):
        return v[:128] if isinstance(v, str) else None

    occ = th.get("anchor_occurrence")
    status = th.get("anchor_status")
    return {
        "anchor_field": field,
        "anchor_quote": quote[:2048],  # ThreadAnchor.quote max_length
        "anchor_prefix": _ctx(th.get("anchor_prefix")),
        "anchor_suffix": _ctx(th.get("anchor_suffix")),
        "anchor_occurrence": occ if isinstance(occ, int) and not isinstance(occ, bool) and 0 <= occ < 10000 else 0,
        "anchor_status": status if status in ("active", "orphaned") else "active",
    }


def _cols(model, *exclude: str) -> list[str]:
    """Every column of ``model`` except ``exclude``. Export lists are derived
    from the models so a new column travels by default; hand-kept lists
    drifted and silently dropped markings, scoring, custom fields etc."""
    return [c.key for c in model.__table__.columns if c.key not in exclude]


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

# Never taken from an archive row: identity, ownership and timestamps the
# import sets itself. Foreign-key columns are skipped too (see below).
_NEVER_FROM_ARCHIVE = frozenset({"id", "engagement_id", "created_by", "updated_by", "updated_at"})
# Attack-graph node id prefixes ("testcase-<uuid>") remapped on import.
_GRAPH_NODE_PREFIXES = frozenset({"testcase", "finding", "asset", "cleanup", "vault", "attacker"})
_SKIP = object()


def _coerce_column(col, v, parse_dt):
    """An archive value checked against the column's type, or _SKIP (the
    column default applies). The archive is untrusted: a wrong type must not
    reach the database, where it would fail the whole import."""
    import sqlalchemy as sa
    from utils.encrypted_types import EncryptedText
    if v is None:
        return None if col.nullable else _SKIP
    t = col.type
    if isinstance(t, sa.DateTime):
        d = parse_dt(v)
        return d if d is not None else (None if col.nullable else _SKIP)
    if isinstance(t, sa.Enum):  # before String: Enum subclasses it
        if isinstance(v, str):
            for cand in (v, v.upper()):
                if cand in t.enums:
                    return cand
        return _SKIP
    if isinstance(t, sa.Boolean):
        return v if isinstance(v, bool) else _SKIP
    if isinstance(t, sa.Integer):
        return v if isinstance(v, int) and not isinstance(v, bool) else _SKIP
    if isinstance(t, sa.Float):
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else _SKIP
    if isinstance(t, sa.JSON):
        return v if isinstance(v, (dict, list)) else _SKIP
    if isinstance(t, (sa.String, EncryptedText)):
        if not isinstance(v, str):
            return _SKIP
        n = getattr(t, "length", None)
        return v[:n] if n else v
    return _SKIP


def _plain_fields(model, row, parse_dt, handled=()) -> dict:
    """The archive row's ordinary columns for ``model``: every column except
    _NEVER_FROM_ARCHIVE, foreign keys (remapped by the caller, never copied)
    and ``handled`` (set explicitly by the caller). Derived from the model so
    new columns round-trip without editing this file."""
    if not isinstance(row, dict):
        return {}
    out = {}
    for col in model.__table__.columns:
        k = col.key
        if k in _NEVER_FROM_ARCHIVE or k in handled or col.foreign_keys or k not in row:
            continue
        v = _coerce_column(col, row[k], parse_dt)
        if v is not _SKIP:
            out[k] = v
    return out


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

    GHSA-3r7j-7h5r-gxgx follow-up: READ_ONLY_ADMIN dropped from the role
    check. Producing a freestanding offline copy — including the vault
    plaintexts the GHSA-3r7j fix now includes — is a stronger action
    than "read-only" implies, and the error message ("Admin or Team Lead
    role required") suggests the inclusion was copy-paste, not intent.
    """
    if current_user.role not in [UserRole.ADMIN, UserRole.TEAM_LEAD]:
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

    GHSA-3r7j-7h5r-gxgx follow-up: READ_ONLY_ADMIN dropped from the role
    check — see the preview endpoint above for the rationale.
    """
    if current_user.role not in [UserRole.ADMIN, UserRole.TEAM_LEAD]:
        raise HTTPException(status_code=403, detail="Admin or Team Lead role required")

    passphrase = _validate_passphrase(x_export_passphrase, kind="export")

    # ── load engagement ──────────────────────────────────────────────
    from models.engagement import Engagement
    result = await db.execute(select(Engagement).where(Engagement.id == engagement_id))
    eng = result.scalar_one_or_none()
    if not eng:
        raise HTTPException(status_code=404, detail="Engagement not found")

    data: dict = {"engagement": _row_dict(eng, _cols(Engagement))}

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
    data["findings"] = [_row_dict(f, _cols(Finding)) for f in findings]
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
    data["finding_assets"] = [_row_dict(r, _cols(FindingAsset)) for r in fa_rows]
    for r in fa_rows:
        _collect_user_ids(r, "remediated_by")

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
    data["assets"] = [_row_dict(a, _cols(Asset)) for a in assets]
    for a in assets:
        _collect_user_ids(a, "created_by", "updated_by")

    # Ports
    p_res = await db.execute(
        select(AssetPort).where(
            AssetPort.asset_id.in_([a.id for a in assets]) if assets else False
        )
    )
    ports = p_res.scalars().all() if assets else []
    data["asset_ports"] = [_row_dict(p, _cols(AssetPort)) for p in ports]

    # ── testcases ────────────────────────────────────────────────────
    from models.testcase import TestCase
    tc_res = await db.execute(
        select(TestCase).options(selectinload(TestCase.tags))
        .where(TestCase.engagement_id == engagement_id)
    )
    testcases = tc_res.scalars().all()
    data["testcases"] = [_row_dict(tc, _cols(TestCase)) for tc in testcases]
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
        _row_dict(r, _cols(TestCaseAsset)) for r in (tca_res.scalars().all() if testcases else [])
    ]

    # ATT&CK technique links (technique ids are global MITRE ids).
    from models.associations import FindingAttackTechnique, TestCaseAttackTechnique
    data["finding_attack_techniques"] = [
        _row_dict(r, _cols(FindingAttackTechnique)) for r in ((await db.execute(
            select(FindingAttackTechnique).where(FindingAttackTechnique.finding_id.in_([f.id for f in findings]))
        )).scalars().all() if findings else [])
    ]
    data["testcase_attack_techniques"] = [
        _row_dict(r, _cols(TestCaseAttackTechnique)) for r in ((await db.execute(
            select(TestCaseAttackTechnique).where(TestCaseAttackTechnique.testcase_id.in_([tc.id for tc in testcases]))
        )).scalars().all() if testcases else [])
    ]

    # Engagement tags, phases, required skills.
    from models.associations import EngagementTag
    from models.engagement_phase import EngagementPhase
    from models.skill import EngagementSkill
    eng_tag_rows = (await db.execute(
        select(EngagementTag).where(EngagementTag.engagement_id == engagement_id))).scalars().all()
    data["engagement_tags"] = [_row_dict(r, _cols(EngagementTag)) for r in eng_tag_rows]
    tag_ids_set.update(r.tag_id for r in eng_tag_rows)
    data["engagement_phases"] = [_row_dict(r, _cols(EngagementPhase)) for r in (await db.execute(
        select(EngagementPhase).where(EngagementPhase.engagement_id == engagement_id))).scalars().all()]
    data["engagement_skills"] = [_row_dict(r, _cols(EngagementSkill)) for r in (await db.execute(
        select(EngagementSkill).where(EngagementSkill.engagement_id == engagement_id))).scalars().all()]

    # ── tags (fetch actual tag objects) ──────────────────────────────
    if tag_ids_set:
        tags_res = await db.execute(select(Tag).where(Tag.id.in_(tag_ids_set)))
        tags = tags_res.scalars().all()
    else:
        tags = []
    data["tags"] = [_row_dict(t, _cols(Tag)) for t in tags]

    # ── evidence ─────────────────────────────────────────────────────
    from models.evidence import Evidence
    ev_res = await db.execute(select(Evidence).where(
        (Evidence.engagement_id == engagement_id) |
        (Evidence.finding_id.in_([f.id for f in findings]) if findings else False) |
        (Evidence.testcase_id.in_([tc.id for tc in testcases]) if testcases else False)
    ))
    evidence_list = ev_res.scalars().all()
    data["evidence"] = [_row_dict(e, _cols(Evidence)) for e in evidence_list]
    for e in evidence_list:
        _collect_user_ids(e, "created_by", "updated_by")

    # ── threads & comments ───────────────────────────────────────────
    from models.discussion import Thread, Comment
    th_res = await db.execute(
        select(Thread).options(selectinload(Thread.comments))
        .where(Thread.engagement_id == engagement_id)
    )
    threads = th_res.scalars().all()
    data["threads"] = [_row_dict(t, _cols(Thread)) for t in threads]
    for t in threads:
        _collect_user_ids(t, "created_by")
    all_comments = []
    for t in threads:
        for c in t.comments:
            all_comments.append(_row_dict(c, _cols(Comment)))
            _collect_user_ids(c, "created_by", "resolved_by")
    data["comments"] = all_comments

    # ── activity logs ────────────────────────────────────────────────
    from models.discussion import ActivityLog
    al_res = await db.execute(select(ActivityLog).where(ActivityLog.engagement_id == engagement_id))
    activity_logs = al_res.scalars().all()
    data["activity_logs"] = [
        _row_dict(a, _cols(ActivityLog, "origin_engagement_id")) for a in activity_logs
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
    vi_fields = _cols(VaultItem, "encryption_version")
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
    from models.associations import VaultItemAsset
    data["vault_item_assets"] = [
        _row_dict(r, _cols(VaultItemAsset)) for r in ((await db.execute(
            select(VaultItemAsset).where(VaultItemAsset.vault_item_id.in_([v.id for v in vault_items]))
        )).scalars().all() if vault_items else [])
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
    data["cleanup_artifacts"] = [_row_dict(ca, _cols(CleanupArtifact)) for ca in cleanup_artifacts]
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
        _row_dict(n, _cols(Note)) for n in notes
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
        _row_dict(an, _cols(AttackerNode)) for an in attacker_nodes
    ]
    ane_res = await db.execute(
        select(AttackerNodeEdge).where(
            AttackerNodeEdge.attacker_node_id.in_([an.id for an in attacker_nodes]) if attacker_nodes else False
        )
    )
    data["attacker_node_edges"] = [
        _row_dict(r, _cols(AttackerNodeEdge)) for r in (ane_res.scalars().all() if attacker_nodes else [])
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
        _row_dict(agl, _cols(AttackGraphLayout, "pinned_by")) for agl in agl_res.scalars().all()
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
        rl_dict = _row_dict(rl, _cols(ReportLayout))
        rl_dict["sections"] = [_row_dict(s, _cols(ReportSection)) for s in rl.sections]
        data["report_layouts"].append(rl_dict)
    for rl in report_layouts:
        _collect_user_ids(rl, "created_by", "updated_by")
    _collect_user_ids(eng, "created_by", "updated_by")

    # ── chain links (testcase / finding / vault item → each other) ───
    from models.chain_link import ChainLink
    chain_links = (await db.execute(
        select(ChainLink).where(ChainLink.engagement_id == engagement_id))).scalars().all()
    data["chain_links"] = [_row_dict(cl, _cols(ChainLink)) for cl in chain_links]
    for cl in chain_links:
        _collect_user_ids(cl, "created_by", "updated_by")

    # ── finding peer reviews ─────────────────────────────────────────
    from models.finding_review import FindingReview
    reviews = (await db.execute(select(FindingReview).where(
        FindingReview.finding_id.in_([f.id for f in findings])))).scalars().all() if findings else []
    data["finding_reviews"] = [_row_dict(r, _cols(FindingReview)) for r in reviews]
    for r in reviews:
        _collect_user_ids(r, "reviewer_id")

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
            "Content-Disposition": content_disposition_attachment(filename),
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
    # Import creates a new engagement + all its child rows, so gate it on the
    # assignable CREATE_ENGAGEMENT (ADMIN bypasses; the Team Leads group grants
    # it). READ_ONLY_ADMIN never passes — it is a write path.
    if not await has_global_permission(current_user, Permission.CREATE_ENGAGEMENT, db):
        raise HTTPException(status_code=403, detail="Insufficient permissions to import an engagement")

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
    manifest = json.loads(_read_member_safely(zf, "manifest.json"))
    if manifest.get("source") != "redwire":
        raise HTTPException(status_code=400, detail="Archive is not a RedWire export")

    # GHSA-vwgf-r8qp-8gwr: verify every archive member against its
    # manifest-recorded SHA-256 BEFORE any further parsing so a
    # tampered engagement.json never reaches the ORM layer.
    _verify_archive_digests(zf, manifest)

    if "engagement.json" not in zf.namelist():
        raise HTTPException(status_code=400, detail="Missing engagement.json in archive")
    data = json.loads(_read_member_safely(zf, "engagement.json"))
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
    # Import creates an engagement — gate on CREATE_ENGAGEMENT (see preview_import).
    if not await has_global_permission(current_user, Permission.CREATE_ENGAGEMENT, db):
        raise HTTPException(status_code=403, detail="Insufficient permissions to import an engagement")

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
    manifest = json.loads(_read_member_safely(zf, "manifest.json"))
    if manifest.get("source") != "redwire":
        raise HTTPException(status_code=400, detail="Archive is not a RedWire export")

    # GHSA-vwgf-r8qp-8gwr: verify every archive member against its
    # manifest-recorded SHA-256 BEFORE any further parsing so a
    # tampered engagement.json never reaches the ORM layer.
    _verify_archive_digests(zf, manifest)

    # Read data
    if "engagement.json" not in zf.namelist():
        raise HTTPException(status_code=400, detail="Missing engagement.json in archive")
    data = json.loads(_read_member_safely(zf, "engagement.json"))

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

    def mapped_user(original_user_id) -> str | None:
        """A manually mapped local user, else None. For attributions that must
        not silently become the importer (a peer approval, a remediation)."""
        mapped = manual_mapping.get(original_user_id) if isinstance(original_user_id, str) else None
        return mapped if mapped in valid_targets else None

    def plain(model, row, handled=()) -> dict:
        return _plain_fields(model, row, parse_dt, handled)

    def rows(key) -> list[dict]:
        v = data.get(key)
        return [r for r in v if isinstance(r, dict)] if isinstance(v, list) else []

    def remap_graph_id(gid) -> str | None:
        """Attack-graph node ids are "<type>-<uuid>"; id_map holds bare ids.
        Infra items are global (not part of the archive) and keep their id."""
        if not isinstance(gid, str):
            return None
        prefix, sep, rest = gid.partition("-")
        if not sep:
            return None
        if prefix == "infra":
            return gid
        if prefix in _GRAPH_NODE_PREFIXES:
            nid = remap(rest)
            return f"{prefix}-{nid}" if nid else None
        return None

    def remap_port_ids(raw) -> str | None:
        """port_ids is a JSON list of AssetPort ids; they were copied verbatim
        and pointed at the source instance's ports."""
        try:
            ids = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError):
            return None
        if not isinstance(ids, list):
            return None
        out = [nid for nid in (remap(x) for x in ids if isinstance(x, str)) if nid]
        return json.dumps(out) if out else None

    async def local_id(model, oid) -> str | None:
        """Keep a reference to an instance-level record (client, marking
        profile, skill) only when it exists here — true for a same-instance
        copy or restore, usually not across instances."""
        if not isinstance(oid, str) or not oid:
            return None
        return (await db.execute(select(model.id).where(model.id == oid))).scalar_one_or_none()

    async def insert_parents_first(items: list[dict], build) -> None:
        """Self-referencing rows (test case / note hierarchy): pre-register
        ids, then insert level by level so each parent exists first. A
        parent outside the archive, or a cycle, imports as top-level."""
        for it in items:
            new_id(it.get("id"))
        known = {it.get("id") for it in items}
        done: set = set()
        pending = list(items)
        while pending:
            ready = [it for it in pending
                     if not it.get("parent_id") or it["parent_id"] in done or it["parent_id"] not in known]
            if not ready:
                for it in pending:
                    it["parent_id"] = None
                ready = pending
            for it in ready:
                db.add(build(it))
                done.add(it.get("id"))
            await db.flush()
            pending = [it for it in pending if it.get("id") not in done]

    uploaded_keys: list[str] = []

    try:
        # ── 1. Engagement ────────────────────────────────────────────
        from models.engagement import Engagement
        from models.client import Client
        from models.marking_profile import MarkingProfile
        eng_data = data["engagement"]
        eng_new_id = new_id(eng_data["id"])

        client_id = await local_id(Client, eng_data.get("client_id"))
        client_name = eng_data.get("client_name") if isinstance(eng_data.get("client_name"), str) else ""
        if client_id:
            client_name = (await db.execute(select(Client.name).where(Client.id == client_id))).scalar_one()
        new_eng = Engagement(
            id=eng_new_id,
            **plain(Engagement, eng_data, handled={"name", "client_name", "engagement_type"}),
            name=str(eng_data["name"]) + " (imported)",
            client_name=client_name or "",
            engagement_type=eng_data.get("engagement_type") if isinstance(eng_data.get("engagement_type"), str) else "Other",
            client_id=client_id,
            marking_profile_id=await local_id(MarkingProfile, eng_data.get("marking_profile_id")),
            created_by=resolve_user(eng_data.get("created_by")),
            updated_by=resolve_user(eng_data.get("updated_by")),
        )
        db.add(new_eng)
        await db.flush()

        # ── 2. Tags — matched by (name, entity_type) ─────────────────
        # Names are unique per entity type, so a name-only lookup raised
        # MultipleResultsFound once a name existed under two types. Archives
        # before 1.3 carry no entity_type: infer it from where the tag is used.
        from models.finding import Tag
        usage: dict = {}
        for key, et in (("finding_tags", "finding"), ("testcase_tags", "testcase"), ("engagement_tags", "engagement")):
            for r in rows(key):
                usage.setdefault(r.get("tag_id"), et)
        for tag_data in rows("tags"):
            name = tag_data.get("name")
            if not isinstance(name, str) or not name.strip() or not tag_data.get("id"):
                continue
            et = tag_data.get("entity_type")
            if not isinstance(et, str) or not et:
                et = usage.get(tag_data["id"], "finding")
            et = et[:20]
            existing_tag = (await db.execute(
                select(Tag).where(Tag.name == name, Tag.entity_type == et).limit(1)
            )).scalars().first()
            if existing_tag:
                id_map[tag_data["id"]] = existing_tag.id
            else:
                db.add(Tag(id=new_id(tag_data["id"]), name=name, entity_type=et,
                           **plain(Tag, tag_data, handled={"name", "entity_type"})))
                await db.flush()

        # ── 3. Assets + ports ────────────────────────────────────────
        from models.asset import Asset
        from models.asset_port import AssetPort
        from utils.asset_types import resolve_asset_type
        for a in rows("assets"):
            db.add(Asset(
                id=new_id(a["id"]),
                engagement_id=eng_new_id,
                **plain(Asset, a, handled={"asset_type", "identifier"}),
                # Same resolution as a direct create: legacy spellings map onto
                # the configured types; with none configured the value is kept.
                asset_type=await resolve_asset_type(
                    a.get("asset_type") if isinstance(a.get("asset_type"), str) else None, db, fallback="Other",
                ) or "Other",
                identifier=a.get("identifier") if isinstance(a.get("identifier"), str) else "",
                created_by=resolve_user(a.get("created_by")),
                updated_by=resolve_user(a.get("updated_by")),
            ))
        await db.flush()
        for p in rows("asset_ports"):
            asset_id = remap(p.get("asset_id"))
            if asset_id is None:
                continue
            db.add(AssetPort(id=new_id(p["id"]), asset_id=asset_id, **plain(AssetPort, p)))
        await db.flush()

        # ── 4. Findings ──────────────────────────────────────────────
        from models.finding import Finding
        finding_author: dict[str, str] = {}
        for f in rows("findings"):
            fid = new_id(f["id"])
            finding_author[fid] = resolve_user(f.get("created_by"))
            db.add(Finding(
                id=fid,
                engagement_id=eng_new_id,
                **plain(Finding, f, handled={"description"}),
                description=f.get("description") if isinstance(f.get("description"), str) else "",
                created_by=finding_author[fid],
                updated_by=resolve_user(f.get("updated_by")),
            ))
        await db.flush()

        # ── 5. TestCases (parent hierarchy) ──────────────────────────
        from models.testcase import TestCase
        await insert_parents_first(rows("testcases"), lambda tc: TestCase(
            id=remap(tc["id"]),
            engagement_id=eng_new_id,
            parent_id=remap(tc.get("parent_id")),
            **plain(TestCase, tc, handled={"category", "description"}),
            category=tc.get("category") if isinstance(tc.get("category"), str) and tc.get("category") else "Other",
            description=tc.get("description") if isinstance(tc.get("description"), str) else "",
            created_by=resolve_user(tc.get("created_by")),
            updated_by=resolve_user(tc.get("updated_by")),
        ))

        # ── 6. Links between findings, test cases, assets, tags ──────
        # A row is kept only when every end was created by this import
        # (a missing end used to insert NULL and fail the whole import).
        from models.associations import (
            FindingAsset, FindingTestCase, FindingTag, TestCaseTag, TestCaseAsset, EngagementTag,
            FindingAttackTechnique, TestCaseAttackTechnique,
            VaultItemFinding, VaultItemTestCase, VaultItemAsset,
            CleanupArtifactFinding, CleanupArtifactTestCase, CleanupArtifactAsset,
            NoteAsset, NoteTestCase, NoteFinding, NoteVaultItem, NoteCleanupArtifact,
        )

        def add_links(key, model, fks: tuple, extra=None):
            seen = set()
            for r in rows(key):
                ends = tuple(remap(r.get(fk)) for fk in fks)
                if None in ends or ends in seen:
                    continue
                seen.add(ends)
                db.add(model(**dict(zip(fks, ends)), **(extra(r) if extra else {})))

        add_links("finding_assets", FindingAsset, ("finding_id", "asset_id"), lambda r: {
            **plain(FindingAsset, r, handled={"port_ids"}),
            "port_ids": remap_port_ids(r.get("port_ids")),
            "remediated_by": mapped_user(r.get("remediated_by")),
        })
        add_links("finding_testcases", FindingTestCase, ("finding_id", "testcase_id"))
        add_links("finding_tags", FindingTag, ("finding_id", "tag_id"))
        add_links("testcase_tags", TestCaseTag, ("testcase_id", "tag_id"))
        add_links("testcase_assets", TestCaseAsset, ("testcase_id", "asset_id"),
                  lambda r: {"port_ids": remap_port_ids(r.get("port_ids"))})
        id_map.setdefault(eng_data["id"], eng_new_id)
        add_links("engagement_tags", EngagementTag, ("engagement_id", "tag_id"))

        # ATT&CK technique ids are global MITRE ids, not remapped.
        for key, model, fk in (("finding_attack_techniques", FindingAttackTechnique, "finding_id"),
                               ("testcase_attack_techniques", TestCaseAttackTechnique, "testcase_id")):
            seen_t = set()
            for r in rows(key):
                owner, tech = remap(r.get(fk)), r.get("technique_id")
                if owner is None or not isinstance(tech, str) or not tech or (owner, tech) in seen_t:
                    continue
                seen_t.add((owner, tech))
                db.add(model(**{fk: owner}, **plain(model, r)))
        await db.flush()

        # ── 6b. Phases, required skills ──────────────────────────────
        from models.engagement_phase import EngagementPhase
        from models.skill import EngagementSkill, Skill
        for ph in rows("engagement_phases"):
            db.add(EngagementPhase(id=new_id(ph.get("id")) or str(uuid.uuid4()), engagement_id=eng_new_id,
                                   **plain(EngagementPhase, ph)))
        for sk in rows("engagement_skills"):
            skill_id = await local_id(Skill, sk.get("skill_id"))
            if skill_id:
                db.add(EngagementSkill(id=str(uuid.uuid4()), engagement_id=eng_new_id, skill_id=skill_id,
                                       **plain(EngagementSkill, sk)))
        await db.flush()

        # ── 7. Evidence (+ upload files) ─────────────────────────────
        from models.evidence import Evidence
        for ev in rows("evidence"):
            old_path = ev.get("file_path") if isinstance(ev.get("file_path"), str) else ""
            zip_path = f"attachments/{old_path}"
            # A row without its file in the archive would point at nothing.
            if not old_path or zip_path not in zf.namelist():
                logger.warning("engagement-import: evidence %r has no file in the archive; skipped", ev.get("id"))
                continue
            ext = os.path.splitext(old_path)[1]
            new_storage_name = f"{uuid.uuid4()}{ext}"
            # The bundle's mime_type is attacker-supplied (text/html on a
            # .png would render inline): derive it from the extension, as a
            # direct upload does.
            ev_mime = safe_content_type(new_storage_name)
            file_bytes = _read_member_safely(zf, zip_path)
            try:
                await storage_service.upload_file(file_bytes, new_storage_name, content_type=ev_mime)
            except Exception:
                # GHSA-rcjp-27mp-v69m: never fall back to the bundle-supplied
                # path — that would persist an attacker-controlled storage
                # key pointing at another engagement's object. Skip the row.
                continue
            uploaded_keys.append(new_storage_name)

            db.add(Evidence(
                id=new_id(ev["id"]),
                finding_id=remap(ev.get("finding_id")),
                testcase_id=remap(ev.get("testcase_id")),
                engagement_id=eng_new_id,
                **plain(Evidence, ev, handled={"filename", "original_filename", "file_path", "file_size", "mime_type"}),
                filename=new_storage_name,
                original_filename=sanitize_original_filename(ev.get("original_filename"), "unknown"),
                file_path=new_storage_name,
                file_size=len(file_bytes),
                mime_type=ev_mime,
                created_by=resolve_user(ev.get("created_by")),
                updated_by=resolve_user(ev.get("updated_by")),
            ))
        await db.flush()

        # ── 8. Vault Items (+ upload files) ──────────────────────────
        from models.vault import VaultItem
        for vi in rows("vault_items"):
            old_path = vi.get("file_path") if isinstance(vi.get("file_path"), str) else ""
            new_vault_path = None
            if old_path:
                ext = os.path.splitext(old_path)[1]
                # GHSA-3r7j-7h5r-gxgx Issue 3 follow-up: force the .enc
                # suffix so the new blob has the same on-disk shape as
                # native uploads (routers/vault.py::upload_vault_file).
                if not ext.endswith(".enc"):
                    ext = (ext or "") + ".enc"
                new_vault_path = f"vault/{uuid.uuid4()}{ext}"
                zip_path = f"attachments/{old_path}"
                if zip_path in zf.namelist():
                    file_bytes = _read_member_safely(zf, zip_path)
                    try:
                        # GHSA-3r7j-7h5r-gxgx Issue 3 follow-up: the archive
                        # carries plaintext; encrypt under THIS instance's
                        # VAULT_ENCRYPTION_KEY before persisting to MinIO.
                        from utils.vault_crypto import encrypt_bytes as _encrypt_vault_bytes
                        await storage_service.upload_file(
                            _encrypt_vault_bytes(file_bytes), new_vault_path,
                            content_type="application/octet-stream",
                        )
                        uploaded_keys.append(new_vault_path)
                    except Exception:
                        # GHSA-rcjp-27mp-v69m: drop the file reference rather
                        # than persisting the attacker-supplied path.
                        new_vault_path = None
                else:
                    new_vault_path = None

            # GHSA-3r7j-7h5r-gxgx: the EncryptedText columns encrypt the
            # archive's plaintext under this instance's key on bind.
            db.add(VaultItem(
                id=new_id(vi["id"]),
                engagement_id=eng_new_id,
                **plain(VaultItem, vi, handled={"file_path", "encryption_version", "item_type"}),
                item_type=vi.get("item_type") if isinstance(vi.get("item_type"), str) and vi.get("item_type") else "Note",
                file_path=new_vault_path,
                # New row's blob (if any) was just encrypted: current scheme.
                encryption_version=1,
                created_by=resolve_user(vi.get("created_by")),
                updated_by=resolve_user(vi.get("updated_by")),
            ))
        await db.flush()
        add_links("vault_item_findings", VaultItemFinding, ("vault_item_id", "finding_id"))
        add_links("vault_item_testcases", VaultItemTestCase, ("vault_item_id", "testcase_id"))
        add_links("vault_item_assets", VaultItemAsset, ("vault_item_id", "asset_id"))
        await db.flush()

        # ── 9. Cleanup Artifacts ─────────────────────────────────────
        from models.cleanup_artifact import CleanupArtifact
        for ca in rows("cleanup_artifacts"):
            db.add(CleanupArtifact(
                id=new_id(ca["id"]),
                engagement_id=eng_new_id,
                **plain(CleanupArtifact, ca, handled={"artifact_type"}),
                artifact_type=ca.get("artifact_type") if isinstance(ca.get("artifact_type"), str) and ca.get("artifact_type") else "Other",
                cleaned_by=resolve_user(ca.get("cleaned_by")) if ca.get("cleaned_by") else None,
                created_by=resolve_user(ca.get("created_by")),
                updated_by=resolve_user(ca.get("updated_by")),
            ))
        await db.flush()
        add_links("cleanup_artifact_findings", CleanupArtifactFinding, ("cleanup_artifact_id", "finding_id"))
        add_links("cleanup_artifact_testcases", CleanupArtifactTestCase, ("cleanup_artifact_id", "testcase_id"))
        add_links("cleanup_artifact_assets", CleanupArtifactAsset, ("cleanup_artifact_id", "asset_id"))
        await db.flush()

        # ── 10. Notes (parent hierarchy) ─────────────────────────────
        from models.note import Note
        await insert_parents_first(rows("notes"), lambda n: Note(
            id=remap(n["id"]),
            engagement_id=eng_new_id,
            parent_id=remap(n.get("parent_id")),
            **plain(Note, n),
            created_by=resolve_user(n.get("created_by")),
            updated_by=resolve_user(n.get("updated_by")),
        ))
        add_links("note_findings", NoteFinding, ("note_id", "finding_id"))
        add_links("note_testcases", NoteTestCase, ("note_id", "testcase_id"))
        add_links("note_assets", NoteAsset, ("note_id", "asset_id"))
        add_links("note_vault_items", NoteVaultItem, ("note_id", "vault_item_id"))
        add_links("note_cleanup_artifacts", NoteCleanupArtifact, ("note_id", "cleanup_artifact_id"))
        await db.flush()

        # ── 10b. Chain links ─────────────────────────────────────────
        from models.chain_link import ChainLink, CHAIN_NODE_TYPES
        for cl in rows("chain_links"):
            src, dst = remap(cl.get("source_id")), remap(cl.get("target_id"))
            if (src is None or dst is None or cl.get("source_type") not in CHAIN_NODE_TYPES
                    or cl.get("target_type") not in CHAIN_NODE_TYPES):
                continue
            db.add(ChainLink(
                id=new_id(cl.get("id")) or str(uuid.uuid4()),
                engagement_id=eng_new_id,
                **plain(ChainLink, cl, handled={"source_id", "target_id"}),
                source_id=src, target_id=dst,
                created_by=resolve_user(cl.get("created_by")),
                updated_by=resolve_user(cl.get("updated_by")),
            ))
        await db.flush()

        # ── 10c. Finding peer reviews ────────────────────────────────
        # Only reviewers mapped to a local user: defaulting them to the
        # importer would forge approvals (possibly on the importer's own
        # findings, defeating the two-person rule).
        from models.finding_review import FindingReview
        seen_reviews = set()
        for rv in rows("finding_reviews"):
            fid, reviewer = remap(rv.get("finding_id")), mapped_user(rv.get("reviewer_id"))
            if (fid is None or reviewer is None or reviewer == finding_author.get(fid)
                    or (fid, reviewer) in seen_reviews or rv.get("status") not in ("APPROVED", "CHANGES_REQUESTED")):
                continue
            seen_reviews.add((fid, reviewer))
            db.add(FindingReview(id=str(uuid.uuid4()), finding_id=fid, reviewer_id=reviewer,
                                 **plain(FindingReview, rv)))
        await db.flush()

        # ── 11. Threads & Comments ───────────────────────────────────
        from models.discussion import Thread, Comment, ResourceType
        # GHSA-7x2f-ff7r-h388 #8 (CWE-20): Thread.resource_type is a plain
        # String(50) with no DB-level enum guard; coerce unknown values to
        # ENGAGEMENT (+ log) rather than refusing the whole archive.
        _valid_resource_types = {v.value for v in ResourceType}
        # Report sections are created in step 15; register their new ids now
        # so report-section threads remap instead of losing their resource.
        for rl in rows("report_layouts"):
            for sec in (rl.get("sections") or []):
                if isinstance(sec, dict):
                    new_id(sec.get("id"))
        for th in rows("threads"):
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
                title=th.get("title") if isinstance(th.get("title"), str) else "",
                is_resolved=th.get("is_resolved") is True,
                created_by=resolve_user(th.get("created_by")),
                created_at=parse_dt(th.get("created_at")) or datetime.utcnow(),
                **_import_anchor(th, raw_rt),
            ))
        await db.flush()

        for c in rows("comments"):
            thread_id = remap(c.get("thread_id"))
            if thread_id is None:
                continue
            db.add(Comment(
                id=new_id(c["id"]),
                thread_id=thread_id,
                **plain(Comment, c, handled={"content"}),
                content=c.get("content") if isinstance(c.get("content"), str) else "",
                resolved_by=resolve_user(c.get("resolved_by")) if c.get("resolved_by") else None,
                created_by=resolve_user(c.get("created_by")),
            ))
        await db.flush()

        # ── 12. Activity Logs ────────────────────────────────────────
        from models.discussion import ActivityLog
        for al in rows("activity_logs"):
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
                action=al.get("action") if isinstance(al.get("action"), str) else "imported",
                resource_type=raw_rt,
                resource_id=remap(al.get("resource_id")) or eng_new_id,
                resource_name=al.get("resource_name") if isinstance(al.get("resource_name"), str) else None,
                details=al.get("details") if isinstance(al.get("details"), str) else None,
                created_at=parse_dt(al.get("created_at")) or datetime.utcnow(),
            ))
        await db.flush()

        # ── 13. Attacker Nodes & Edges ───────────────────────────────
        from models.attacker_node import AttackerNode, AttackerNodeEdge
        for an in rows("attacker_nodes"):
            db.add(AttackerNode(id=new_id(an["id"]), engagement_id=eng_new_id, **plain(AttackerNode, an)))
        await db.flush()

        for edge in rows("attacker_node_edges"):
            attacker_node_id = remap(edge.get("attacker_node_id"))
            ttype = edge.get("target_node_type") if isinstance(edge.get("target_node_type"), str) else ""
            raw_target = edge.get("target_node_id")
            # Stored as the graph id ("testcase-<uuid>"); very old rows may be bare.
            target = remap_graph_id(raw_target)
            if target is None and remap(raw_target) and ttype in _GRAPH_NODE_PREFIXES:
                target = f"{ttype}-{remap(raw_target)}"
            if attacker_node_id is None or target is None:
                continue
            db.add(AttackerNodeEdge(
                id=new_id(edge.get("id")) or str(uuid.uuid4()),
                attacker_node_id=attacker_node_id,
                target_node_id=target,
                target_node_type=ttype,
            ))
        await db.flush()

        # ── 14. Attack Graph Layouts ─────────────────────────────────
        # New archives ship a list (`attack_graph_layouts`); old archives
        # ship a single object (`attack_graph_layout`).
        agl_list = data.get("attack_graph_layouts")
        if agl_list is None:
            single = data.get("attack_graph_layout")
            agl_list = [single] if single else []
        from models.attack_graph_layout import AttackGraphLayout
        for agl_data in agl_list if isinstance(agl_list, list) else []:
            if not isinstance(agl_data, dict):
                continue
            positions_raw = agl_data.get("positions", "{}")
            try:
                positions = json.loads(positions_raw) if isinstance(positions_raw, str) else positions_raw
            except (TypeError, ValueError):
                positions = {}
            # Keys are graph node ids; those not in this archive are dropped.
            remapped_pos = {}
            for key, value in (positions.items() if isinstance(positions, dict) else []):
                nk = remap_graph_id(key)
                if nk:
                    remapped_pos[nk] = value
            db.add(AttackGraphLayout(
                id=new_id(agl_data.get("id")) or str(uuid.uuid4()),
                engagement_id=eng_new_id,
                **plain(AttackGraphLayout, agl_data, handled={"positions", "name"}),
                name=agl_data.get("name") if isinstance(agl_data.get("name"), str) and agl_data.get("name") else "Default",
                positions=json.dumps(remapped_pos),
                pinned_by=current_user.id,
            ))
        await db.flush()

        # ── 15. Report Layouts ───────────────────────────────────────
        from models.report_layout import ReportLayout, ReportSection
        for rl in rows("report_layouts"):
            rl_new_id = new_id(rl["id"])
            db.add(ReportLayout(
                id=rl_new_id,
                engagement_id=eng_new_id,
                **plain(ReportLayout, rl, handled={"name"}),
                name=rl.get("name") if isinstance(rl.get("name"), str) and rl.get("name") else "Default",
                created_by=resolve_user(rl.get("created_by")),
                updated_by=resolve_user(rl.get("updated_by")),
            ))
            await db.flush()
            for sec in (rl.get("sections") or []):
                if not isinstance(sec, dict):
                    continue
                db.add(ReportSection(
                    id=new_id(sec.get("id")) or str(uuid.uuid4()),
                    report_layout_id=rl_new_id,
                    **plain(ReportSection, sec, handled={"title"}),
                    title=sec.get("title") if isinstance(sec.get("title"), str) else "",
                ))
            await db.flush()

        # ── Log import activity ──────────────────────────────────────
        # GHSA-vwgf-r8qp-8gwr: include the archive's manifest root
        # digest so forensic queries can tie an imported engagement
        # back to a specific archive.
        _archive_fp = (manifest.get("root_digest") or "unknown")[:16]
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
        # The rows are gone; so must be the objects uploaded for them.
        for key in uploaded_keys:
            try:
                await storage_service.delete_file(key)
            except Exception:
                logger.warning("engagement-import: could not remove orphaned object %s", key)
        if isinstance(e, HTTPException):
            raise
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Import failed: {str(e)}"
        )
