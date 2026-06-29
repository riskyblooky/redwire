from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List, Optional
import logging

from database import get_db
from models.user import User, UserRole
from models.engagement import Engagement
from models.spray import SprayCampaign, SprayResult
from models.vault import VaultItem
from schemas.spray import (
    SprayImportPreview, SprayResultPreview, SprayCommitRequest,
    SprayCampaignResponse, SprayCampaignDetailResponse,
)
from auth.dependencies import get_current_user
from auth.rbac import check_engagement_permission
from models.permission import Permission
# SprayCampaign.password_used and SprayResult.username/password are
# EncryptedText columns — encrypt-on-write happens at the ORM type
# layer, so this router passes raw plaintext into the constructors.
from utils.collaboration import create_activity_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/spray", tags=["spray"])


# ── Import (preview) ────────────────────────────────────────────

@router.post("/import", response_model=SprayImportPreview)
async def import_spray_log(
    file: UploadFile = File(...),
    engagement_id: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload a NetExec log file and return a preview of parsed results."""
    # Verify engagement exists
    result = await db.execute(select(Engagement).where(Engagement.id == engagement_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Engagement not found")

    # Permission check
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_perm = await check_engagement_permission(
            current_user.id, engagement_id, Permission.VAULT_CREATE.value, db
        )
        if not has_perm:
            raise HTTPException(status_code=403, detail="Insufficient permissions")

    # Read and parse
    content = await file.read()
    try:
        text = content.decode("utf-8", errors="replace")
    except Exception:
        raise HTTPException(status_code=400, detail="Could not decode file as text")

    from utils.parsers.netexec import parse_netexec_log
    parsed = parse_netexec_log(text)

    if parsed.total_attempts == 0:
        raise HTTPException(
            status_code=400,
            detail="No spray results found in the file. Ensure this is a NetExec/CrackMapExec log."
        )

    # Cross-check the hosts the spray touched against the engagement's
    # current asset inventory so the UI can show "N already in scope, M
    # new" before commit.
    from models.asset import Asset
    asset_q = await db.execute(
        select(Asset.identifier).where(Asset.engagement_id == engagement_id)
    )
    existing_identifiers = {row for row in asset_q.scalars().all() if row}

    distinct_hosts = {r.target_host for r in parsed.results if r.target_host}
    matched_hosts = distinct_hosts & existing_identifiers
    unmatched_hosts = sorted(distinct_hosts - existing_identifiers)

    return SprayImportPreview(
        protocol=parsed.protocol,
        target_host=parsed.target_host,
        target_port=parsed.target_port,
        target_hostname=parsed.target_hostname,
        domain=parsed.domain,
        password_used=parsed.password_used,
        total_attempts=parsed.total_attempts,
        successful=parsed.successful,
        locked_out=parsed.locked_out,
        failed=parsed.failed,
        host_count=parsed.host_count,
        command_line=parsed.command_line,
        matched_asset_count=len(matched_hosts),
        unmatched_hosts=unmatched_hosts,
        imported_from=file.filename,
        results=[
            SprayResultPreview(
                username=r.username,
                domain=r.domain,
                result=r.result,
                status_code=r.status_code,
                is_admin=r.is_admin,
                target_host=r.target_host,
                target_port=r.target_port,
                password=r.password,
            )
            for r in parsed.results
        ],
    )


# ── Commit ───────────────────────────────────────────────────────

@router.post("/commit", response_model=SprayCampaignResponse, status_code=201)
async def commit_spray(
    data: SprayCommitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Commit previewed spray results — creates campaign + result rows."""
    # Verify engagement
    result = await db.execute(select(Engagement).where(Engagement.id == data.engagement_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Engagement not found")

    # Permission check
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_perm = await check_engagement_permission(
            current_user.id, data.engagement_id, Permission.VAULT_CREATE.value, db
        )
        if not has_perm:
            raise HTTPException(status_code=403, detail="Insufficient permissions")

    # Create campaign — password_used is encrypted on bind by the
    # EncryptedText column type.
    total = len(data.results)
    successful = sum(1 for r in data.results if r.result.startswith("success"))
    locked_out = sum(1 for r in data.results if r.result == "locked")
    failed = total - successful - locked_out

    campaign = SprayCampaign(
        engagement_id=data.engagement_id,
        name=data.name,
        protocol=data.protocol,
        target_host=data.target_host,
        target_port=data.target_port,
        target_hostname=data.target_hostname,
        domain=data.domain,
        password_used=data.password_used,
        total_attempts=total,
        successful=successful,
        locked_out=locked_out,
        failed=failed,
        status="imported",
        notes=data.notes,
        imported_from=data.imported_from,
        created_by=current_user.id,
    )
    db.add(campaign)
    await db.flush()  # get campaign.id

    # Build/extend the asset inventory before adding results so we can FK
    # each result to its matching asset in one pass.
    from models.asset import Asset

    # Distinct, non-null hosts seen in this run.
    spray_hosts = {r.target_host for r in data.results if r.target_host}

    # Existing assets in the engagement, keyed by identifier.
    existing_q = await db.execute(
        select(Asset).where(Asset.engagement_id == data.engagement_id)
    )
    asset_by_identifier: dict[str, Asset] = {
        a.identifier: a for a in existing_q.scalars().all() if a.identifier
    }

    # Optionally inventory the hosts we sprayed but haven't seen before.
    created_assets = 0
    if data.create_missing_assets:
        for host in sorted(spray_hosts - asset_by_identifier.keys()):
            new_asset = Asset(
                engagement_id=data.engagement_id,
                name=host,
                asset_type="IP_ADDRESS",
                identifier=host,
                description=f"Auto-created from spray campaign: {data.name}",
                in_scope=True,
                is_scanned=True,        # spray is itself a form of scan
                created_by=current_user.id,
            )
            db.add(new_asset)
            asset_by_identifier[host] = new_asset
            created_assets += 1
        if created_assets:
            await db.flush()  # populate IDs before referencing as FK

    # Create result rows. EncryptedText encrypts username + password
    # at bind time under the same Fernet key as campaign.password_used.
    linked_results = 0
    for r in data.results:
        linked_asset = asset_by_identifier.get(r.target_host) if r.target_host else None
        if linked_asset is not None:
            linked_results += 1
        db.add(SprayResult(
            campaign_id=campaign.id,
            username=r.username,
            domain=r.domain,
            result=r.result,
            status_code=r.status_code,
            is_admin=r.is_admin,
            target_host=r.target_host,
            target_port=r.target_port,
            password=r.password,
            asset_id=linked_asset.id if linked_asset else None,
        ))

    await db.commit()
    await db.refresh(campaign)

    # Log activity
    await create_activity_log(
        db,
        engagement_id=data.engagement_id,
        user_id=current_user.id,
        action="imported_spray",
        resource_type="spray",
        resource_id=campaign.id,
        resource_name=campaign.name,
        details=(
            f"Imported spray campaign: {campaign.name} "
            f"({total} attempts, {successful} hits, {linked_results} linked to assets"
            + (f", {created_assets} assets created" if created_assets else "")
            + ")"
        ),
    )

    return campaign


# ── List campaigns ───────────────────────────────────────────────

@router.get("/campaigns", response_model=List[SprayCampaignResponse])
async def list_spray_campaigns(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List spray campaigns for an engagement."""
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_perm = await check_engagement_permission(
            current_user.id, engagement_id, Permission.VAULT_VIEW.value, db
        )
        if not has_perm:
            raise HTTPException(status_code=403, detail="Insufficient permissions")

    result = await db.execute(
        select(SprayCampaign)
        .where(SprayCampaign.engagement_id == engagement_id)
        .order_by(SprayCampaign.created_at.desc())
    )
    campaigns = result.scalars().all()

    # EncryptedText already decrypted password_used at ORM-read time.
    return campaigns


# ── Get campaign detail ──────────────────────────────────────────

@router.get("/campaigns/{campaign_id}", response_model=SprayCampaignDetailResponse)
async def get_spray_campaign(
    campaign_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a spray campaign with all results."""
    result = await db.execute(
        select(SprayCampaign)
        .options(selectinload(SprayCampaign.results))
        .where(SprayCampaign.id == campaign_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Spray campaign not found")

    # Permission check
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_perm = await check_engagement_permission(
            current_user.id, campaign.engagement_id, Permission.VAULT_VIEW.value, db
        )
        if not has_perm:
            raise HTTPException(status_code=403, detail="Insufficient permissions")

    # EncryptedText already decrypted password_used at ORM-read time.
    return campaign


# ── Delete campaign ──────────────────────────────────────────────

@router.delete("/campaigns/{campaign_id}", status_code=204)
async def delete_spray_campaign(
    campaign_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a spray campaign and all its results."""
    result = await db.execute(
        select(SprayCampaign).where(SprayCampaign.id == campaign_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Spray campaign not found")

    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_perm = await check_engagement_permission(
            current_user.id, campaign.engagement_id, Permission.VAULT_DELETE.value, db
        )
        if not has_perm:
            raise HTTPException(status_code=403, detail="Insufficient permissions")

    # Log before delete
    await create_activity_log(
        db,
        engagement_id=campaign.engagement_id,
        user_id=current_user.id,
        action="deleted_spray",
        resource_type="spray",
        resource_id=campaign.id,
        resource_name=campaign.name,
        details=f"Deleted spray campaign: {campaign.name}",
    )

    await db.delete(campaign)
    await db.commit()
    return None


# ── Auto-vault hits ──────────────────────────────────────────────

@router.post("/campaigns/{campaign_id}/vault-hits")
async def vault_spray_hits(
    campaign_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Auto-create VaultItem credentials for successful spray results."""
    result = await db.execute(
        select(SprayCampaign)
        .options(selectinload(SprayCampaign.results))
        .where(SprayCampaign.id == campaign_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Spray campaign not found")

    # Permission check
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_perm = await check_engagement_permission(
            current_user.id, campaign.engagement_id, Permission.VAULT_CREATE.value, db
        )
        if not has_perm:
            raise HTTPException(status_code=403, detail="Insufficient permissions")

    # EncryptedText already decrypted campaign.password_used at ORM-read.
    # Kept as a fallback for older per-result rows that didn't store
    # their own password (pre per-result-schema imports).
    campaign_password = campaign.password_used

    # Find successful results not yet vaulted
    to_vault = [
        r for r in campaign.results
        if r.result.startswith("success") and not r.vault_item_id
    ]

    if not to_vault:
        return {"vaulted": 0, "message": "No new hits to vault"}

    # Pre-load engagement assets so we can match per-result hosts to assets.
    from models.asset import Asset
    asset_q = await db.execute(
        select(Asset).where(Asset.engagement_id == campaign.engagement_id)
    )
    engagement_assets = asset_q.scalars().all()
    asset_by_identifier = {a.identifier: a for a in engagement_assets if a.identifier}

    vaulted = 0
    for spray_result in to_vault:
        # Resolve the actual password for this specific hit:
        #   1. Per-result password (correct for wordlist runs) — already
        #      decrypted by EncryptedText on ORM read.
        #   2. Campaign-level password (fallback for legacy/single-pwd runs).
        result_password = spray_result.password or campaign_password

        username_display = f"{spray_result.domain}\\{spray_result.username}" if spray_result.domain else spray_result.username
        host_tag = f"@{spray_result.target_host}" if spray_result.target_host else ""

        # Resolve the asset to link BEFORE constructing the VaultItem so we
        # can pass it in via the constructor. Reading vault_item.assets after
        # flush triggers a sync lazy-load that crashes in async context.
        match_host = spray_result.target_host or campaign.target_host
        matching_asset = asset_by_identifier.get(match_host) if match_host else None

        # is_admin info goes in the description (kept off the name) so users
        # can still surface "this credential gives admin access on target" via
        # search/filter without it cluttering the vault item title.
        admin_note = " (admin shell)" if spray_result.is_admin else ""

        # EncryptedText on VaultItem.{username,password} encrypts on bind.
        vault_item = VaultItem(
            engagement_id=campaign.engagement_id,
            name=f"{username_display}{host_tag}",
            item_type="CREDENTIAL",
            username=username_display,
            password=result_password,
            description=f"Auto-vaulted from spray campaign: {campaign.name}{admin_note}",
            created_by=current_user.id,
            assets=[matching_asset] if matching_asset else [],
        )
        db.add(vault_item)
        await db.flush()

        # Update spray result with vault reference
        spray_result.vault_item_id = vault_item.id
        vaulted += 1

    await db.commit()

    # Log activity
    await create_activity_log(
        db,
        engagement_id=campaign.engagement_id,
        user_id=current_user.id,
        action="vaulted_spray_hits",
        resource_type="spray",
        resource_id=campaign.id,
        resource_name=campaign.name,
        details=f"Auto-vaulted {vaulted} credentials from spray campaign: {campaign.name}",
    )

    return {"vaulted": vaulted, "message": f"{vaulted} credentials added to vault"}
