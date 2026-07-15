from fastapi import APIRouter, Depends, HTTPException, status, Response, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List
import json
import os
import zipfile
import io
import tempfile
import logging
import traceback
from datetime import datetime

logger = logging.getLogger(__name__)


# GHSA-q8q6-22jx-7rjj: aggregate-size guard for evidence in JSON_ZIP /
# JSON_LAYOUT_ZIP exports. With the SpooledTemporaryFile + StreamingResponse
# refactor this is now a *policy* limit ("we don't ship reports larger than
# this to clients") rather than a *safety* limit ("we OOM above this") —
# the archive rolls to a tempfile above ``_ZIP_SPOOL_THRESHOLD`` and
# streams chunked from disk, so memory pressure is bounded regardless
# of evidence aggregate size. Default sized for a typical small
# engagement; tune via env without code change.
REPORT_EXPORT_MAX_EVIDENCE_BYTES = int(
    os.getenv("REPORT_EXPORT_MAX_EVIDENCE_BYTES", str(50 * 1024 * 1024))
)

# In-memory threshold for ``SpooledTemporaryFile``. Archives smaller than
# this stay in memory (fast path for the common small-export case).
# Larger archives roll over to a real tempfile under ``/tmp`` and stream
# chunked from disk on the response side.
_ZIP_SPOOL_THRESHOLD = 10 * 1024 * 1024

# Per-read chunk size when streaming the archive back to the client.
# 64 KiB matches the chunking discipline in ``utils.uploads.read_upload_capped``.
_ZIP_STREAM_CHUNK = 64 * 1024


def _stream_spooled_zip(spooled: tempfile.SpooledTemporaryFile):
    """Generator that yields the archive in fixed-size chunks and closes
    the spooled tempfile when the iterator is exhausted (or cancelled).

    ``SpooledTemporaryFile`` deletes its on-disk backing file when
    ``close()`` is called, so cleanup is automatic — but the generator
    has to run to completion (or get GC'd) for that to fire. Streaming
    via a ``StreamingResponse`` does run it to completion in the normal
    case; the ``finally`` covers client-aborts the response."""
    try:
        while True:
            chunk = spooled.read(_ZIP_STREAM_CHUNK)
            if not chunk:
                break
            yield chunk
    finally:
        spooled.close()


def _safe_arcname(name: str) -> str:
    """GHSA-fwvp-qc8h-r5p4: reduce a stored filename to a basename suitable
    for use as a ZIP member name or manifest path. Strips any directory
    components (including Windows backslashes) and neutralises a residual
    ``..`` after the basename so an extractor can't write outside the
    chosen target directory.
    """
    cleaned = os.path.basename((name or "").replace("\\", "/"))
    cleaned = cleaned.replace("..", "_")
    return cleaned or "unnamed"

from database import get_db
from models.user import User
from models.engagement import Engagement
from models.finding import Finding, Tag
from models.evidence import Evidence
from models.testcase import TestCase
from models.cleanup_artifact import CleanupArtifact
from models.custom_field_definition import CustomFieldDefinition
from models.report_layout import ReportLayout, ReportSection, SectionType
from models.report_theme import ReportTheme
from models.marking_profile import MarkingProfile
from schemas.report import ReportConfiguration, ReportFormat
from auth.dependencies import get_current_user
from auth.rbac import check_engagement_permission
from models.permission import Permission
from models.user import UserRole
from utils.report_generator import PDFReportGenerator, MarkdownReportGenerator, HTMLReportGenerator
from utils.storage import storage_service
from utils.uploads import safe_content_type

router = APIRouter(prefix="/reports", tags=["reports"])

@router.post("/generate")
async def generate_report(
    config: ReportConfiguration,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Generate a report based on the selected layout and theme."""
    try:
        return await _do_generate_report(config, db, current_user)
    except HTTPException:
        raise
    except Exception as e:
        # Don't leak the underlying exception text in the HTTP response —
        # it was an error oracle in GHSA-vm9w-7vpv-2jpm (open/closed/non-image
        # distinction → port scan + filesystem enumeration). The traceback
        # stays in server logs for operators to investigate.
        logger.error(f"Report generation failed: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Report generation failed. Check server logs for details.",
        )


async def _do_generate_report(
    config: ReportConfiguration,
    db: AsyncSession,
    current_user: User,
):

    # 1. Fetch Engagement
    result = await db.execute(
        select(Engagement)
        .where(Engagement.id == config.engagement_id)
        .options(selectinload(Engagement.assigned_users))
    )
    engagement = result.scalar_one_or_none()

    if not engagement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Engagement not found"
        )

    # Check permissions
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_permission = await check_engagement_permission(current_user.id, config.engagement_id, Permission.REPORT_GENERATE.value, db)
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. You need the 'report_generate' permission to generate reports."
            )

    # 2. Fetch Layout with sections
    layout_result = await db.execute(
        select(ReportLayout)
        .where(ReportLayout.id == config.layout_id, ReportLayout.engagement_id == config.engagement_id)
        .options(selectinload(ReportLayout.sections))
    )
    layout = layout_result.scalar_one_or_none()
    if not layout:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report layout not found for this engagement"
        )

    # Sort sections by sort_order
    sections = sorted(layout.sections, key=lambda s: s.sort_order)

    # 3. Fetch Theme — three-stage resolution (GHSA-3m9c-7f84-9cm2 follow-up):
    #    (a) explicit theme_id from the request
    #    (b) any user-marked default (is_default=True)
    #    (c) the seeded system theme (is_system=True) as an ultimate
    #        fallback so an admin who deleted the current default doesn't
    #        break every subsequent report generation. Delete guard in
    #        routers/report_themes.py prevents deleting the system row,
    #        but this belt-and-suspenders keeps report_generator working
    #        even if the row goes missing (drift, hand-edited DB, etc.).
    theme = None
    if config.theme_id:
        theme_result = await db.execute(
            select(ReportTheme).where(ReportTheme.id == config.theme_id)
        )
        theme = theme_result.scalar_one_or_none()
    if not theme:
        default_result = await db.execute(
            select(ReportTheme).where(ReportTheme.is_default == True)
        )
        theme = default_result.scalar_one_or_none()
    if not theme:
        system_result = await db.execute(
            select(ReportTheme).where(ReportTheme.is_system == True)
        )
        theme = system_result.scalar_one_or_none()

    # 3b. Resolve the marking profile: explicit config → engagement's profile →
    # None. Marking is OPT-IN: with no profile selected, no markings render.
    marking_profile = None
    chosen_profile_id = config.marking_profile_id or engagement.marking_profile_id
    if chosen_profile_id:
        mp_result = await db.execute(
            select(MarkingProfile).where(MarkingProfile.id == chosen_profile_id)
        )
        marking_profile = mp_result.scalar_one_or_none()

    # 4. Fetch Findings
    findings_query = (
        select(Finding)
        .where(Finding.engagement_id == config.engagement_id)
        .options(
            selectinload(Finding.assets),
            selectinload(Finding.evidence),
            selectinload(Finding.tags),
        )
    )
    if config.exclude_severities:
        findings_query = findings_query.where(Finding.severity.notin_(config.exclude_severities))
    findings_result = await db.execute(findings_query)
    findings = list(findings_result.scalars().all())
    if config.finding_ids is not None:
        finding_id_set = set(config.finding_ids)
        findings = [f for f in findings if str(f.id) in finding_id_set]

    # 4b. Report-visible finding custom fields (show_in_report only). Passed
    # into the generators so per-finding cards render them; DB-free generators
    # get the definitions precomputed here, matching the theme/profile pattern.
    finding_cf_result = await db.execute(
        select(CustomFieldDefinition)
        .where(
            CustomFieldDefinition.entity_type == "finding",
            CustomFieldDefinition.show_in_report == True,  # noqa: E712
            CustomFieldDefinition.is_active == True,  # noqa: E712
        )
        .order_by(CustomFieldDefinition.position)
    )
    finding_custom_fields = list(finding_cf_result.scalars().all())

    # 5. Fetch Test Cases
    testcases_result = await db.execute(
        select(TestCase)
        .where(TestCase.engagement_id == config.engagement_id)
        .options(selectinload(TestCase.tags))
        .order_by(TestCase.category, TestCase.title)
    )
    testcases = list(testcases_result.scalars().all())
    if config.testcase_ids is not None:
        testcase_id_set = set(config.testcase_ids)
        testcases = [tc for tc in testcases if str(tc.id) in testcase_id_set]

    # 6. Fetch Cleanup Artifacts
    cleanup_result = await db.execute(
        select(CleanupArtifact)
        .where(CleanupArtifact.engagement_id == config.engagement_id)
        .options(selectinload(CleanupArtifact.assets))
        .order_by(CleanupArtifact.title)
    )
    cleanup_artifacts = list(cleanup_result.scalars().all())
    if config.cleanup_ids is not None:
        cleanup_id_set = set(config.cleanup_ids)
        cleanup_artifacts = [ca for ca in cleanup_artifacts if str(ca.id) in cleanup_id_set]

    # 6b. Marking enforcement lint (WARN / BLOCK). Only meaningful when a
    # profile with levels is in effect.
    marking_warning_headers = {}
    if marking_profile and (marking_profile.levels or []):
        from utils.marking import MarkingEngine, lint_marking
        engine = MarkingEngine(marking_profile, engagement)
        enforcement = getattr(marking_profile.enforcement, 'value', marking_profile.enforcement)
        if enforcement in ('WARN', 'BLOCK'):
            blocking, warnings = lint_marking(engine, sections, findings, testcases, cleanup_artifacts)
            if enforcement == 'BLOCK' and blocking:
                logger.info(f"Report generation blocked by marking enforcement: {len(blocking)} unmarked portion(s)")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Marking enforcement is set to BLOCK and {len(blocking)} portion(s) have no "
                        f"classification (no explicit mark and no engagement default). Set an engagement "
                        f"default classification or mark these items: " + "; ".join(blocking[:15])
                        + ("…" if len(blocking) > 15 else "")
                    ),
                )
            # WARN (or BLOCK with no blockers): surface inherited-default count.
            warn_count = len(warnings) + (len(blocking) if enforcement == 'WARN' else 0)
            if warn_count:
                marking_warning_headers["X-Marking-Warnings"] = str(warn_count)

    # 7. Generate Report
    safe_name = engagement.name.replace(' ', '_').replace('/', '_')

    # Pre-fetch markdown-image rows for this engagement so the PDF
    # generator can resolve inline `<img src="/api/markdown-images/...">`
    # references to MinIO storage keys without further DB access.
    from models.markdown_image import MarkdownImage
    md_img_result = await db.execute(
        select(MarkdownImage).where(MarkdownImage.engagement_id == engagement.id)
    )
    markdown_image_map = {
        row.id: {
            "storage_key": row.storage_key,
            "content_type": row.content_type,
        }
        for row in md_img_result.scalars().all()
    }

    # Lifecycle hook — plugins can subscribe to react to a completed
    # report (push to a document store, notify a Slack channel, etc.).
    # Fired BEFORE the rendered bytes leave the process so any exception
    # in a subscriber becomes visible before we commit to the response.
    # Payload deliberately omits the rendered bytes themselves — those
    # can be gigabytes; give subscribers the metadata to fetch or
    # re-render as needed.
    try:
        from utils.event_bus import event_bus
        await event_bus.emit("report.generated", {
            "engagement_id": engagement.id,
            "engagement_name": engagement.name,
            "user_id": current_user.id,
            "layout_id": layout.id,
            "layout_name": getattr(layout, "name", None),
            "theme_id": theme.id if theme else None,
            "marking_profile_id": chosen_profile_id,
            "format": config.report_format.value,
            "finding_count": len(findings),
        })
    except Exception as _e:
        print(f"[reports] report.generated event emit error (non-fatal): {_e}")

    if config.report_format == ReportFormat.PDF:
        generator = PDFReportGenerator(engagement, sections, findings, testcases, cleanup_artifacts, theme, storage=storage_service, markdown_image_map=markdown_image_map, marking_profile=marking_profile, finding_custom_fields=finding_custom_fields)
        pdf_content = generator.generate()
        filename = f"Report_{safe_name}.pdf"
        return Response(
            content=pdf_content,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"', **marking_warning_headers}
        )

    elif config.report_format == ReportFormat.MARKDOWN:
        generator = MarkdownReportGenerator(engagement, sections, findings, testcases, cleanup_artifacts, theme, finding_custom_fields=finding_custom_fields)
        md_content = generator.generate()
        filename = f"Report_{safe_name}.md"
        return Response(
            content=md_content,
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="{filename}"', **marking_warning_headers}
        )

    elif config.report_format == ReportFormat.HTML:
        generator = HTMLReportGenerator(engagement, sections, findings, testcases, cleanup_artifacts, theme, storage=storage_service, markdown_image_map=markdown_image_map, marking_profile=marking_profile, finding_custom_fields=finding_custom_fields)
        html_content = generator.generate()
        filename = f"Report_{safe_name}.html"
        return Response(
            content=html_content,
            media_type="text/html",
            headers={"Content-Disposition": f'attachment; filename="{filename}"', **marking_warning_headers}
        )

    elif config.report_format in (ReportFormat.JSON_ZIP, ReportFormat.JSON_LAYOUT_ZIP):
        # Also fetch standalone engagement evidence (not tied to a finding)
        standalone_evidence_result = await db.execute(
            select(Evidence)
            .where(Evidence.engagement_id == config.engagement_id, Evidence.finding_id == None)
        )
        standalone_evidence = list(standalone_evidence_result.scalars().all())

        # Build structured export data
        export_data = {
            "exported_at": datetime.utcnow().isoformat() + "Z",
            "engagement": {
                "id": engagement.id,
                "name": engagement.name,
                "client_name": engagement.client_name,
                "engagement_type": engagement.engagement_type,
                "status": engagement.status.value if engagement.status else None,
                "description": engagement.description,
                "scope": engagement.scope,
                "objectives": engagement.objectives,
                "start_date": engagement.start_date.isoformat() if engagement.start_date else None,
                "end_date": engagement.end_date.isoformat() if engagement.end_date else None,
                "created_at": engagement.created_at.isoformat() if engagement.created_at else None,
                "updated_at": engagement.updated_at.isoformat() if engagement.updated_at else None,
            },
            "findings": [
                {
                    "id": f.id,
                    "title": f.title,
                    "severity": f.severity.value if f.severity else None,
                    "status": f.status.value if f.status else None,
                    "category": f.category,
                    "custom_fields": f.custom_fields or {},
                    "description": f.description,
                    "impact": f.impact,
                    "technical_details": f.technical_details,
                    "steps_to_reproduce": f.steps_to_reproduce,
                    "mitigations": f.mitigations,
                    "references": f.references,
                    "cvss_score": f.cvss_score,
                    "cvss_vector": f.cvss_vector,
                    "created_at": f.created_at.isoformat() if f.created_at else None,
                    "updated_at": f.updated_at.isoformat() if f.updated_at else None,
                    "tags": [{"id": t.id, "name": t.name, "color": t.color} for t in (f.tags or [])],
                    "assets": [{"id": a.id, "name": a.name, "identifier": a.identifier} for a in (f.assets or [])],
                    "evidence": [
                        {
                            "id": e.id,
                            "original_filename": e.original_filename,
                            "mime_type": e.mime_type,
                            "file_size": e.file_size,
                            "description": e.description,
                            "include_in_report": e.include_in_report,
                            "attachment_path": f"attachments/findings/{f.id}/{_safe_arcname(e.original_filename)}" if e.include_in_report else None,
                        }
                        for e in (f.evidence or [])
                    ],
                }
                for f in findings
            ],
            "testcases": [
                {
                    "id": tc.id,
                    "parent_id": tc.parent_id,
                    "title": tc.title,
                    "category": tc.category,
                    "description": tc.description,
                    "steps": tc.steps,
                    "expected_result": tc.expected_result,
                    "actual_result": tc.actual_result,
                    "is_executed": tc.is_executed,
                    "is_successful": tc.is_successful,
                    "notes": tc.notes,
                    "created_at": tc.created_at.isoformat() if tc.created_at else None,
                    "updated_at": tc.updated_at.isoformat() if tc.updated_at else None,
                    "tags": [{"id": t.id, "name": t.name, "color": t.color} for t in (tc.tags or [])],
                }
                for tc in testcases
            ],
            "cleanup_artifacts": [
                {
                    "id": ca.id,
                    "title": ca.title,
                    "artifact_type": ca.artifact_type,
                    "status": ca.status.value if ca.status else None,
                    "location": ca.location,
                    "description": ca.description,
                    "cleanup_notes": ca.cleanup_notes,
                    "cleaned_at": ca.cleaned_at.isoformat() if ca.cleaned_at else None,
                    "created_at": ca.created_at.isoformat() if ca.created_at else None,
                    "assets": [{"id": a.id, "name": a.name, "identifier": a.identifier} for a in (ca.assets or [])],
                }
                for ca in cleanup_artifacts
            ],
            "standalone_evidence": [
                {
                    "id": e.id,
                    "original_filename": e.original_filename,
                    "mime_type": e.mime_type,
                    "file_size": e.file_size,
                    "description": e.description,
                    "include_in_report": e.include_in_report,
                    "attachment_path": f"attachments/engagement/{_safe_arcname(e.original_filename)}" if e.include_in_report else None,
                }
                for e in standalone_evidence
            ],
        }

        # For JSON_LAYOUT_ZIP, also emit the layout structure so consumers
        # can render in the same section order / TEXT-section content as the
        # PDF and Markdown formats. Resource sections (findings/testcases/
        # cleanup_artifacts) just signal the type — the actual records live
        # in the top-level arrays above (which are already filtered by the
        # frontend's per-resource selection).
        if config.report_format == ReportFormat.JSON_LAYOUT_ZIP:
            export_data["layout"] = {
                "id": layout.id,
                "name": layout.name,
                "is_default": layout.is_default,
                "sections": [
                    {
                        "type": s.section_type.value,
                        "title": s.title,
                        "sort_order": s.sort_order,
                        "content": s.content if s.section_type == SectionType.TEXT else None,
                    }
                    for s in sections
                ],
            }

        # Build the archive into a spooled tempfile so memory usage stays
        # bounded regardless of evidence aggregate size — the response
        # side streams chunks back via ``StreamingResponse`` rather than
        # materialising the whole archive as one ``bytes`` payload.
        # Failures unwind via the explicit ``except: close()`` below;
        # the normal-completion close runs inside ``_stream_spooled_zip``
        # when the streaming generator exhausts.
        spooled = tempfile.SpooledTemporaryFile(
            max_size=_ZIP_SPOOL_THRESHOLD, mode="w+b"
        )
        try:
            with zipfile.ZipFile(spooled, 'w', zipfile.ZIP_DEFLATED) as zf:
                # Write JSON
                json_content = json.dumps(export_data, indent=2, ensure_ascii=False)
                zf.writestr("engagement_export.json", json_content)

                # Download and bundle evidence files
                if config.include_evidence:
                    # GHSA-q8q6-22jx-7rjj: sum recorded file sizes from the DB row
                    # before any MinIO round-trip. include_in_report mirrors what
                    # the loops below will write, so the cap matches what the
                    # archive would otherwise have grown to.
                    #
                    # Defense-in-depth over the recorded size: HEAD each object
                    # first and use ``max(recorded, actual)``. An operator with
                    # direct MinIO access could have swapped in a larger file
                    # after upload, defeating the cap if we trusted the DB
                    # value alone. One HEAD per file is cheap (metadata only,
                    # no body transfer); missing objects return None and
                    # fall back to the recorded value.
                    async def _effective_size(e) -> int:
                        recorded = e.file_size or 0
                        meta = await storage_service.head_object(e.filename)
                        actual = (meta or {}).get("size") or 0
                        return max(recorded, actual)

                    finding_evidence_bytes = 0
                    for f in findings:
                        for e in (f.evidence or []):
                            if e.include_in_report and e.filename:
                                finding_evidence_bytes += await _effective_size(e)

                    standalone_evidence_bytes = 0
                    for e in standalone_evidence:
                        if e.include_in_report and e.filename:
                            standalone_evidence_bytes += await _effective_size(e)

                    total_evidence_bytes = finding_evidence_bytes + standalone_evidence_bytes
                    if total_evidence_bytes > REPORT_EXPORT_MAX_EVIDENCE_BYTES:
                        logger.warning(
                            "Refused JSON_ZIP export of engagement %s by user %s: "
                            "%d evidence bytes > %d cap",
                            engagement.id, current_user.id,
                            total_evidence_bytes, REPORT_EXPORT_MAX_EVIDENCE_BYTES,
                        )
                        raise HTTPException(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail=(
                                f"Evidence export aggregate "
                                f"({total_evidence_bytes // (1024*1024)} MiB) exceeds "
                                f"the {REPORT_EXPORT_MAX_EVIDENCE_BYTES // (1024*1024)} "
                                "MiB limit. Deselect 'include evidence' or reduce the "
                                "engagement's evidence set."
                            ),
                        )

                    # Finding evidence
                    for f in findings:
                        for e in (f.evidence or []):
                            if e.include_in_report and e.filename:
                                try:
                                    file_bytes = await storage_service.download_file(e.filename)
                                    safe_name = _safe_arcname(e.original_filename)
                                    if safe_name != (e.original_filename or ""):
                                        logger.warning(
                                            "GHSA-fwvp: sanitized evidence %s original_filename %r → %r for ZIP export",
                                            e.id, e.original_filename, safe_name,
                                        )
                                    zf.writestr(f"attachments/findings/{f.id}/{safe_name}", file_bytes)
                                except Exception:
                                    pass  # Skip files that can't be downloaded

                    # Standalone engagement evidence
                    for e in standalone_evidence:
                        if e.include_in_report and e.filename:
                            try:
                                file_bytes = await storage_service.download_file(e.filename)
                                safe_name = _safe_arcname(e.original_filename)
                                if safe_name != (e.original_filename or ""):
                                    logger.warning(
                                        "GHSA-fwvp: sanitized standalone evidence %s original_filename %r → %r for ZIP export",
                                        e.id, e.original_filename, safe_name,
                                    )
                                zf.writestr(f"attachments/engagement/{safe_name}", file_bytes)
                            except Exception:
                                pass
        except Exception:
            # Anything that escapes the build phase (DB read, MinIO outage,
            # HTTPException for cap breach) — release the tempfile before
            # the exception unwinds the request.
            spooled.close()
            raise

        spooled.seek(0)
        filename = f"Export_{safe_name}.zip"
        return StreamingResponse(
            _stream_spooled_zip(spooled),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Unsupported report format"
    )


@router.post("/save-to-engagement")
async def save_report_to_engagement(
    file: UploadFile = File(...),
    engagement_id: str = Form(...),
    filename: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Save a generated report as an engagement attachment.

    Accepts the report blob, uploads it to storage, and creates an Evidence
    record linked to the engagement (standalone — no finding).  The saved
    report will appear in the engagement's Attachments tab.
    """
    from models.evidence import Evidence
    import uuid, os

    # 1. Verify engagement exists
    result = await db.execute(
        select(Engagement).where(Engagement.id == engagement_id)
    )
    engagement = result.scalar_one_or_none()
    if not engagement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Engagement not found",
        )

    # 2. Permission check (same as report generation)
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_permission = await check_engagement_permission(
            current_user.id,
            engagement_id,
            Permission.REPORT_GENERATE.value,
            db,
        )
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions to save reports for this engagement.",
            )

    # 3. Read file content
    content = await file.read()
    file_size = len(content)

    # 4. Upload to MinIO
    ext = os.path.splitext(filename)[1] if filename else ""
    storage_filename = f"{uuid.uuid4()}{ext}"
    # GHSA-h77m-pjqc-5cm3 follow-up: server-derived MIME, not the client's
    # Content-Type header. Stored on MinIO and on the Evidence row that
    # the frontend reads for inline-preview decisions.
    safe_mime = safe_content_type(filename)
    try:
        await storage_service.upload_file(
            content, storage_filename, content_type=safe_mime
        )
    except Exception as e:
        logger.error(f"Storage upload failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Storage failure: {str(e)}",
        )

    # 5. Create Evidence record (standalone engagement attachment)
    new_evidence = Evidence(
        engagement_id=engagement_id,
        filename=storage_filename,
        original_filename=filename,
        file_path=storage_filename,
        file_size=file_size,
        mime_type=safe_mime,
        description=f"Generated report: {filename}",
        include_in_report=True,
        created_by=current_user.id,
    )
    db.add(new_evidence)
    await db.commit()
    await db.refresh(new_evidence)

    # 6. Log activity
    from utils.collaboration import create_activity_log

    await create_activity_log(
        db,
        engagement_id=engagement_id,
        user_id=current_user.id,
        action="saved_report",
        resource_type="evidence",
        resource_id=new_evidence.id,
        resource_name=filename,
        details=f"Saved generated report as attachment: {filename}",
    )

    return {
        "id": new_evidence.id,
        "filename": filename,
        "file_size": file_size,
        "message": "Report saved to engagement attachments",
    }
