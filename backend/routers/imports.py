"""
routers/imports.py — Scanner Import Router

Two-step import flow:
  1. POST /imports/preview  → dry-run parse, returns preview data (no DB writes)
  2. POST /imports/commit   → creates assets + findings in the target engagement
"""

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select
from typing import Optional
from database import get_db
from models.user import User, UserRole
from models.permission import Permission
from auth.rbac import check_engagement_permission, require_engagement_perm
from models.asset import Asset
from utils.asset_types import canonical_name, configured_asset_types
from models.asset_port import AssetPort, PortProtocol, PortState
from models.finding import Finding, Severity, FindingStatus
from auth.dependencies import get_current_user
from schemas.imports import (
    PreviewResponse, PreviewAsset, PreviewFinding, PreviewPort,
    CommitResponse, ScanImportResponse,
)
from models.scan_import import ScanImport
from utils.parsers import detect_and_parse, ParsedImportData, render_instances
from utils.asset_identity import identifier_key, load_assets_by_key, normalize_identifier
from utils.collaboration import create_activity_log
from utils.uploads import read_upload_capped
import logging
import os
import uuid

_log = logging.getLogger(__name__)


router = APIRouter(prefix="/imports", tags=["imports"])


def _scanner_import_max_bytes() -> int:
    """Resolve the per-request size cap for scanner imports. Defaults to
    50 MB (the pre-cap behaviour) but admins can lower or raise it via
    ``SCANNER_IMPORT_MAX_BYTES`` without redeploying. GHSA-h77m-pjqc-5cm3
    follow-up: the previous read-then-check pattern still allocated the
    full body in memory before tripping the 413, so the cap was a
    cosmetic gate against the multi-GB DoS — ``read_upload_capped``
    bails the moment the running total crosses the threshold."""
    raw = os.environ.get("SCANNER_IMPORT_MAX_BYTES", "").strip()
    if not raw:
        return 50 * 1024 * 1024
    try:
        return int(raw)
    except ValueError:
        return 50 * 1024 * 1024


# ─── Helpers ──────────────────────────────────────────────────────────────────

_SEVERITY_ENUM = {
    "CRITICAL": Severity.CRITICAL,
    "HIGH": Severity.HIGH,
    "MEDIUM": Severity.MEDIUM,
    "LOW": Severity.LOW,
    "INFO": Severity.INFO,
}


def _parsed_to_preview(
    parsed: ParsedImportData,
    existing_identifiers: set[str],
    existing_titles: set[str],
) -> PreviewResponse:
    """Convert ParsedImportData to API preview response with dedup flags."""
    preview_assets = []
    for i, a in enumerate(parsed.assets):
        preview_assets.append(PreviewAsset(
            index=i,
            name=a.name,
            asset_type=a.asset_type,
            identifier=a.identifier,
            description=a.description,
            ports=[PreviewPort(
                port_number=p.port_number,
                protocol=p.protocol,
                service_name=p.service_name,
                state=p.state,
                version=p.version,
            ) for p in a.ports],
            is_duplicate=identifier_key(a.identifier) in existing_identifiers,
        ))

    preview_findings = []
    for i, f in enumerate(parsed.findings):
        preview_findings.append(PreviewFinding(
            index=i,
            title=f.title,
            severity=f.severity,
            description=f.description,
            impact=f.impact,
            mitigations=f.mitigations,
            references=f.references,
            cvss_score=f.cvss_score,
            cvss_vector=f.cvss_vector,
            category=f.category,
            affected_asset_count=len(f.affected_asset_indices),
            is_duplicate=f.title.lower() in existing_titles,
        ))

    return PreviewResponse(
        source_tool=parsed.source_tool,
        assets=preview_assets,
        findings=preview_findings,
        warnings=parsed.warnings,
        metadata=parsed.raw_metadata,
    )


async def _check_import_permission(current_user: User, engagement_id: str, db: AsyncSession):
    """Ensure the user can import (i.e. has asset_create access)."""
    # Write gate: READ_ONLY_ADMIN views everything but only writes with an explicit grant.
    await require_engagement_perm(current_user, engagement_id, Permission.ASSET_CREATE, db, action="import scans")


# ─── Preview Endpoint ────────────────────────────────────────────────────────

@router.post("/preview", response_model=PreviewResponse)
async def preview_import(
    file: UploadFile = File(...),
    engagement_id: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Dry-run parse of a scanner output file.
    Returns parsed assets and findings with duplicate indicators.
    No database writes.
    """
    # If the caller scopes the preview to a specific engagement, they
    # need permission on that engagement — otherwise the response leaks
    # the foreign engagement's asset identifiers and finding titles via
    # the dedup pass below (RDW-100, follow-up to GHSA-ghw9-87v2-9453).
    # When no engagement_id is supplied, the parse is still gated to
    # authenticated callers and writes no DB rows; the underlying
    # XML-bomb risk it ran against is closed by defusedxml.
    if engagement_id:
        await _check_import_permission(current_user, engagement_id, db)

    max_bytes = _scanner_import_max_bytes()
    content = await read_upload_capped(
        file,
        max_bytes,
        detail=f"Scanner import file too large. Maximum {max_bytes} bytes "
               "(override with SCANNER_IMPORT_MAX_BYTES).",
    )
    filename = file.filename or "unknown"

    try:
        parsed = detect_and_parse(content, filename)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to parse file: {e}",
        )

    # Get existing identifiers/titles for dedup check
    existing_identifiers: set[str] = set()
    existing_titles: set[str] = set()

    if engagement_id:
        # Existing assets
        asset_result = await db.execute(
            select(Asset.identifier).where(Asset.engagement_id == engagement_id)
        )
        existing_identifiers = {
            identifier_key(row[0]) for row in asset_result.all() if row[0]
        }

        # Existing findings
        finding_result = await db.execute(
            select(Finding.title).where(Finding.engagement_id == engagement_id)
        )
        existing_titles = {
            row[0].lower() for row in finding_result.all() if row[0]
        }

    return _parsed_to_preview(parsed, existing_identifiers, existing_titles)


# ─── Commit Endpoint ─────────────────────────────────────────────────────────

@router.post("/commit", response_model=CommitResponse)
async def commit_import(
    file: UploadFile = File(...),
    engagement_id: str = Form(...),
    import_assets: bool = Form(True),
    import_findings: bool = Form(True),
    asset_indices: Optional[str] = Form(None),      # JSON array string
    finding_indices: Optional[str] = Form(None),     # JSON array string
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Commit parsed scanner output to the database.
    Creates assets, ports, findings, and finding→asset links.
    """
    import json as json_mod

    await _check_import_permission(current_user, engagement_id, db)

    max_bytes = _scanner_import_max_bytes()
    content = await read_upload_capped(
        file,
        max_bytes,
        detail=f"Scanner import file too large. Maximum {max_bytes} bytes "
               "(override with SCANNER_IMPORT_MAX_BYTES).",
    )
    filename = file.filename or "unknown"

    try:
        parsed = detect_and_parse(content, filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to parse file: {e}")

    # Parse optional index filters
    selected_asset_idx: set[int] | None = None
    selected_finding_idx: set[int] | None = None

    if asset_indices:
        try:
            selected_asset_idx = set(json_mod.loads(asset_indices))
        except (json_mod.JSONDecodeError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid asset_indices format.")

    if finding_indices:
        try:
            selected_finding_idx = set(json_mod.loads(finding_indices))
        except (json_mod.JSONDecodeError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid finding_indices format.")

    # Get existing assets for dedup
    existing_assets = await load_assets_by_key(db, engagement_id, with_ports=True)

    # Existing findings by title, for dedup. A re-import of a known finding
    # still links it to any hosts it's newly seen on.
    existing_finding_result = await db.execute(
        select(Finding).where(Finding.engagement_id == engagement_id).options(selectinload(Finding.assets))
    )
    existing_findings: dict[str, Finding] = {}
    for f in existing_finding_result.scalars().all():
        if f.title:
            existing_findings.setdefault(f.title.lower(), f)

    result = CommitResponse()

    # ── Phase 1: Create Assets ───────────────────────────────────────────
    # Maps parsed asset index → database Asset object
    asset_map: dict[int, Asset] = {}

    if import_assets:
        type_names = await configured_asset_types(db)
        # (port, protocol) keys per asset identifier for this whole batch.
        # Ports added here go in by asset_id and never show up in
        # Asset.ports, so a second parsed asset with the same identifier
        # (Burp vhosts on one IP, a host listed twice) would re-insert them
        # and hit the asset_ports unique constraint.
        port_keys: dict[str, dict] = {
            ident: {(p.port_number, p.protocol): p for p in a.ports}
            for ident, a in existing_assets.items()
        }

        def add_ports(db_asset: Asset, identifier_lower: str, ports) -> None:
            seen = port_keys.setdefault(identifier_lower, {})
            for p in ports:
                proto = PortProtocol.UDP if p.protocol == "UDP" else PortProtocol.TCP
                state = PortState.OPEN
                if p.state == "CLOSED":
                    state = PortState.CLOSED
                elif p.state == "FILTERED":
                    state = PortState.FILTERED
                known = seen.get((p.port_number, proto))
                if known is not None:
                    # A newer scan of a known port: take what it observed,
                    # without blanking details it didn't report.
                    known.state = state
                    known.service_name = p.service_name or known.service_name
                    known.version = p.version or known.version
                    continue
                port = AssetPort(
                    id=str(uuid.uuid4()),
                    asset_id=db_asset.id,
                    port_number=p.port_number,
                    protocol=proto,
                    service_name=p.service_name,
                    state=state,
                    version=p.version,
                )
                db.add(port)
                seen[(p.port_number, proto)] = port
                result.ports_added += 1

        for i, parsed_asset in enumerate(parsed.assets):
            if selected_asset_idx is not None and i not in selected_asset_idx:
                continue

            identifier_lower = identifier_key(parsed_asset.identifier)

            if identifier_lower in existing_assets:
                # Asset exists (in the engagement or earlier in this file) — merge ports
                db_asset = existing_assets[identifier_lower]
                asset_map[i] = db_asset
                add_ports(db_asset, identifier_lower, parsed_asset.ports)
                if parsed.source_tool in ("nmap", "httpx", "nxc"):
                    db_asset.is_scanned = True
                result.assets_skipped += 1
            else:
                # Create new asset
                # Port/service discovery tools mark the asset as scanned.
                is_port_scan = parsed.source_tool in ("nmap", "httpx", "nxc")
                db_asset = Asset(
                    id=str(uuid.uuid4()),
                    engagement_id=engagement_id,
                    name=parsed_asset.name,
                    asset_type=canonical_name(parsed_asset.asset_type, type_names) or parsed_asset.asset_type,
                    identifier=normalize_identifier(parsed_asset.identifier),
                    description=parsed_asset.description,
                    is_scanned=is_port_scan,
                    created_by=current_user.id,
                )
                db.add(db_asset)
                add_ports(db_asset, identifier_lower, parsed_asset.ports)

                existing_assets[identifier_lower] = db_asset
                asset_map[i] = db_asset
                result.assets_created += 1
    else:
        # Even if not importing assets, map existing ones for finding links
        for i, parsed_asset in enumerate(parsed.assets):
            identifier_lower = identifier_key(parsed_asset.identifier)
            if identifier_lower in existing_assets:
                asset_map[i] = existing_assets[identifier_lower]

    # Flush to get asset IDs
    await db.flush()

    # ── Phase 2: Create Findings ─────────────────────────────────────────
    if import_findings:
        asset_labels = {i: a.identifier for i, a in enumerate(parsed.assets)}
        for i, parsed_finding in enumerate(parsed.findings):
            if selected_finding_idx is not None and i not in selected_finding_idx:
                continue

            # Dedup by title; a known finding picks up hosts it's new on.
            known = existing_findings.get(parsed_finding.title.lower())
            if known is not None:
                new_idx = set()
                for asset_idx in parsed_finding.affected_asset_indices:
                    asset = asset_map.get(asset_idx)
                    if asset is not None and asset not in known.assets:
                        known.assets.append(asset)
                        new_idx.add(asset_idx)
                        result.finding_asset_links += 1
                # The evidence for hosts it's new on goes with them.
                added = render_instances(
                    [x for x in parsed_finding.instances if x.asset_index in new_idx], asset_labels)
                if added:
                    known.technical_details = "\n\n".join(p for p in (known.technical_details, added) if p)
                result.findings_skipped += 1
                continue

            sev = _SEVERITY_ENUM.get(parsed_finding.severity, Severity.INFO)

            # Clamp CVSS
            cvss = parsed_finding.cvss_score
            if cvss is not None:
                cvss = max(0.0, min(10.0, cvss))

            db_finding = Finding(
                id=str(uuid.uuid4()),
                engagement_id=engagement_id,
                title=parsed_finding.title,
                category=parsed_finding.category,
                description=parsed_finding.description or f"Imported from {parsed.source_tool}",
                severity=sev,
                status=FindingStatus.OPEN,
                cvss_score=cvss,
                cvss_vector=parsed_finding.cvss_vector,
                impact=parsed_finding.impact,
                mitigations=parsed_finding.mitigations,
                references=parsed_finding.references,
                # Per-host evidence (port / location and the scanner's output
                # for each host); the parser merged the hosts into one finding.
                technical_details=render_instances(parsed_finding.instances, asset_labels) or None,
                created_by=current_user.id,
            )
            db.add(db_finding)

            # Link finding to assets
            for asset_idx in parsed_finding.affected_asset_indices:
                if asset_idx in asset_map:
                    db_finding.assets.append(asset_map[asset_idx])
                    result.finding_asset_links += 1

            existing_findings[parsed_finding.title.lower()] = db_finding
            result.findings_created += 1

    await db.commit()

    # Log activity
    source = parsed.source_tool.upper()
    details_parts = []
    if result.assets_created:
        details_parts.append(f"{result.assets_created} assets created")
    if result.assets_skipped:
        details_parts.append(f"{result.assets_skipped} assets merged")
    if result.findings_created:
        details_parts.append(f"{result.findings_created} findings created")
    if result.findings_skipped:
        details_parts.append(f"{result.findings_skipped} findings skipped (duplicates)")
    if result.ports_added:
        details_parts.append(f"{result.ports_added} ports added")

    try:
        await create_activity_log(
            db,
            engagement_id=engagement_id,
            user_id=current_user.id,
            action="imported_scan",
            resource_type="import",
            resource_id="",
            resource_name=f"{source} Import",
            details=f"Imported {source} scan: {', '.join(details_parts)}",
        )
    except Exception:  # Don't fail the import if activity logging fails
        _log.exception("Activity log for a scan import failed")

    # Persist a scan-import record so the command + scan metadata survive the
    # import and can be revisited in the scans menu. Best-effort — a failure
    # here must not fail the import itself.
    try:
        meta = parsed.raw_metadata or {}

        def _as_int(v):
            try:
                return int(v)
            except (TypeError, ValueError):
                return None

        def _as_float(v):
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        hosts_total = meta.get("hosts_total")
        if hosts_total is None:
            hosts_total = meta.get("total_hosts")

        scan = ScanImport(
            engagement_id=engagement_id,
            source_tool=parsed.source_tool,
            source_format=meta.get("format") or None,
            filename=filename,
            command=(meta.get("args") or meta.get("command") or None),  # nxc stores "command"
            scanner=(meta.get("scanner") or None),
            scanner_version=(meta.get("version") or None),
            started_at=(meta.get("start") or None),
            finished_at=(meta.get("finished") or None),
            elapsed_seconds=_as_float(meta.get("elapsed")),
            summary=(meta.get("summary") or None),
            hosts_total=_as_int(hosts_total),
            hosts_up=_as_int(meta.get("hosts_up")),
            hosts_down=_as_int(meta.get("hosts_down")),
            assets_created=result.assets_created,
            assets_merged=result.assets_skipped,
            findings_created=result.findings_created,
            ports_added=result.ports_added,
            created_by=current_user.id,
        )
        # SAVEPOINT: a failed insert rolls back the record alone. It used to
        # leave the session failed (swallowed, no rollback), so the raw-file
        # attachment below broke and the import returned a 500.
        async with db.begin_nested():
            db.add(scan)
        await db.commit()
        result.scan_import_id = scan.id
    except Exception:
        _log.exception("Saving the scan-import record failed (import itself succeeded)")

    # Retain the raw scan file as an engagement attachment (best-effort, excluded
    # from the report). The original file is preserved for the record alongside
    # the parsed assets/findings.
    from utils.attachments import save_bytes_as_evidence
    await save_bytes_as_evidence(
        db,
        engagement_id=engagement_id,
        content=content,
        original_filename=filename,
        user_id=current_user.id,
        description=f"{source} scan source file (auto-saved on import)",
        include_in_report=False,
    )

    return result


@router.get("/scans", response_model=list[ScanImportResponse])
async def list_scan_imports(
    engagement_id: str,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List past scanner imports for an engagement (most recent first), with the
    command line + scan metadata captured at import time."""
    # A read: ASSET_VIEW (read-only admins included), not the import write gate.
    if current_user.role not in (UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD) \
            and not await check_engagement_permission(current_user.id, engagement_id, Permission.ASSET_VIEW.value, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions for this engagement.")

    limit = max(1, min(limit, 200))
    rows = (await db.execute(
        select(ScanImport, User.username, User.full_name)
        .outerjoin(User, ScanImport.created_by == User.id)
        .where(ScanImport.engagement_id == engagement_id)
        .order_by(ScanImport.created_at.desc())
        .offset(offset)
        .limit(limit)
    )).all()

    out = []
    for scan, username, full_name in rows:
        d = ScanImportResponse.model_validate(scan).model_dump()
        d["created_by_username"] = username
        d["created_by_full_name"] = full_name
        out.append(d)
    return out
