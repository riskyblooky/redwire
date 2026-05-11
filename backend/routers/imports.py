"""
routers/imports.py — Scanner Import Router

Two-step import flow:
  1. POST /imports/preview  → dry-run parse, returns preview data (no DB writes)
  2. POST /imports/commit   → creates assets + findings in the target engagement
"""

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from database import get_db
from models.user import User, UserRole
from models.permission import Permission
from auth.rbac import check_engagement_permission
from models.asset import Asset
from models.asset_port import AssetPort, PortProtocol, PortState
from models.finding import Finding, Severity, FindingStatus
from auth.dependencies import get_current_user
from schemas.imports import (
    PreviewResponse, PreviewAsset, PreviewFinding, PreviewPort,
    CommitResponse,
)
from utils.parsers import detect_and_parse, ParsedImportData
from utils.collaboration import create_activity_log
import uuid


router = APIRouter(prefix="/imports", tags=["imports"])


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
            is_duplicate=a.identifier.lower() in existing_identifiers,
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
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_permission = await check_engagement_permission(
            current_user.id, engagement_id, Permission.ASSET_CREATE.value, db
        )
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions to import scans.",
            )


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
    content = await file.read()
    filename = file.filename or "unknown"

    if len(content) > 50 * 1024 * 1024:  # 50 MB limit
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large. Maximum 50 MB.",
        )

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
            row[0].lower() for row in asset_result.all() if row[0]
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

    content = await file.read()
    filename = file.filename or "unknown"

    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large. Maximum 50 MB.",
        )

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
    existing_result = await db.execute(
        select(Asset).where(Asset.engagement_id == engagement_id)
    )
    existing_assets = {a.identifier.lower(): a for a in existing_result.scalars().all()}

    # Get existing finding titles for dedup
    existing_finding_result = await db.execute(
        select(Finding.title).where(Finding.engagement_id == engagement_id)
    )
    existing_titles = {row[0].lower() for row in existing_finding_result.all() if row[0]}

    result = CommitResponse()

    # ── Phase 1: Create Assets ───────────────────────────────────────────
    # Maps parsed asset index → database Asset object
    asset_map: dict[int, Asset] = {}

    if import_assets:
        for i, parsed_asset in enumerate(parsed.assets):
            if selected_asset_idx is not None and i not in selected_asset_idx:
                continue

            identifier_lower = parsed_asset.identifier.lower()

            if identifier_lower in existing_assets:
                # Asset exists — merge ports
                db_asset = existing_assets[identifier_lower]
                asset_map[i] = db_asset
                existing_port_keys = {
                    (p.port_number, p.protocol) for p in db_asset.ports
                }

                for p in parsed_asset.ports:
                    proto = PortProtocol.UDP if p.protocol == "UDP" else PortProtocol.TCP
                    if (p.port_number, proto) not in existing_port_keys:
                        state = PortState.OPEN
                        if p.state == "CLOSED":
                            state = PortState.CLOSED
                        elif p.state == "FILTERED":
                            state = PortState.FILTERED

                        db_port = AssetPort(
                            id=str(uuid.uuid4()),
                            asset_id=db_asset.id,
                            port_number=p.port_number,
                            protocol=proto,
                            service_name=p.service_name,
                            state=state,
                            version=p.version,
                        )
                        db.add(db_port)
                        existing_port_keys.add((p.port_number, proto))
                        result.ports_added += 1

                result.assets_skipped += 1
            else:
                # Create new asset
                is_nmap = parsed.source_tool == "nmap"
                db_asset = Asset(
                    id=str(uuid.uuid4()),
                    engagement_id=engagement_id,
                    name=parsed_asset.name,
                    asset_type=parsed_asset.asset_type,
                    identifier=parsed_asset.identifier,
                    description=parsed_asset.description,
                    is_scanned=is_nmap,
                    created_by=current_user.id,
                )
                db.add(db_asset)

                # Add ports
                for p in parsed_asset.ports:
                    proto = PortProtocol.UDP if p.protocol == "UDP" else PortProtocol.TCP
                    state = PortState.OPEN
                    if p.state == "CLOSED":
                        state = PortState.CLOSED
                    elif p.state == "FILTERED":
                        state = PortState.FILTERED

                    db_port = AssetPort(
                        id=str(uuid.uuid4()),
                        asset_id=db_asset.id,
                        port_number=p.port_number,
                        protocol=proto,
                        service_name=p.service_name,
                        state=state,
                        version=p.version,
                    )
                    db.add(db_port)
                    result.ports_added += 1

                existing_assets[identifier_lower] = db_asset
                asset_map[i] = db_asset
                result.assets_created += 1
    else:
        # Even if not importing assets, map existing ones for finding links
        for i, parsed_asset in enumerate(parsed.assets):
            identifier_lower = parsed_asset.identifier.lower()
            if identifier_lower in existing_assets:
                asset_map[i] = existing_assets[identifier_lower]

    # Flush to get asset IDs
    await db.flush()

    # ── Phase 2: Create Findings ─────────────────────────────────────────
    if import_findings:
        for i, parsed_finding in enumerate(parsed.findings):
            if selected_finding_idx is not None and i not in selected_finding_idx:
                continue

            # Dedup by title
            if parsed_finding.title.lower() in existing_titles:
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
                created_by=current_user.id,
            )
            db.add(db_finding)

            # Link finding to assets
            for asset_idx in parsed_finding.affected_asset_indices:
                if asset_idx in asset_map:
                    db_finding.assets.append(asset_map[asset_idx])
                    result.finding_asset_links += 1

            existing_titles.add(parsed_finding.title.lower())
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
    except Exception:
        pass  # Don't fail the import if activity logging fails

    return result
