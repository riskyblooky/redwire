"""
ATT&CK router — engagement-level coverage, AI technique suggestion,
and ATT&CK Navigator JSON export.
"""

import json
import logging
import re
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from pydantic import BaseModel

from database import get_db
from models.user import User, UserRole
from models.finding import Finding
from models.testcase import TestCase
from models.associations import FindingAttackTechnique, TestCaseAttackTechnique
from auth.dependencies import get_current_user
from auth.rbac import check_engagement_permission
from models.permission import Permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/attack", tags=["attack"])


# ── Schemas ───────────────────────────────────────────────────────────

class SuggestRequest(BaseModel):
    finding_ids: list[str] = []


# ── Coverage ──────────────────────────────────────────────────────────

@router.get("/engagement/{engagement_id}/coverage")
async def get_attack_coverage(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get ATT&CK technique coverage for an engagement.

    Returns all techniques mapped to engagement findings, grouped by
    technique ID, plus counts of mapped vs. unmapped findings.
    """
    from models.engagement import Engagement

    # Verify engagement exists
    eng_result = await db.execute(
        select(Engagement).where(Engagement.id == engagement_id)
    )
    engagement = eng_result.scalar_one_or_none()
    if not engagement:
        raise HTTPException(404, "Engagement not found")

    # Fetch all findings for this engagement with their techniques
    findings_result = await db.execute(
        select(Finding)
        .where(Finding.engagement_id == engagement_id)
        .options(selectinload(Finding.attack_techniques))
    )
    findings = findings_result.scalars().all()

    # Fetch all testcases for this engagement with their techniques
    testcases_result = await db.execute(
        select(TestCase)
        .where(TestCase.engagement_id == engagement_id)
        .options(selectinload(TestCase.attack_techniques))
    )
    testcases = testcases_result.scalars().all()

    # Build coverage maps — track findings and testcases independently per
    # technique so the UI can split them across sub-tabs.
    findings_by_technique: dict[str, list[dict]] = {}
    testcases_by_technique: dict[str, list[dict]] = {}
    mapped_technique_set: set[str] = set()
    mapped_finding_ids: set[str] = set()
    mapped_testcase_ids: set[str] = set()

    for f in findings:
        for at in (f.attack_techniques or []):
            tid = at.technique_id
            mapped_technique_set.add(tid)
            mapped_finding_ids.add(f.id)
            findings_by_technique.setdefault(tid, []).append({
                "id": f.id,
                "title": f.title,
                "severity": f.severity.value if f.severity else None,
                "status": f.status.value if f.status else None,
            })

    for tc in testcases:
        for at in (tc.attack_techniques or []):
            tid = at.technique_id
            mapped_technique_set.add(tid)
            mapped_testcase_ids.add(tc.id)
            testcases_by_technique.setdefault(tid, []).append({
                "id": tc.id,
                "title": tc.title,
                "category": tc.category,
                "is_executed": bool(tc.is_executed),
                "is_successful": tc.is_successful,
            })

    return {
        "mapped_techniques": sorted(mapped_technique_set),
        "findings_by_technique": findings_by_technique,
        "testcases_by_technique": testcases_by_technique,
        "total_findings": len(findings),
        "mapped_findings": len(mapped_finding_ids),
        "unmapped_findings": len(findings) - len(mapped_finding_ids),
        "total_testcases": len(testcases),
        "mapped_testcases": len(mapped_testcase_ids),
        "unmapped_testcases": len(testcases) - len(mapped_testcase_ids),
    }


# ── AI Suggest ────────────────────────────────────────────────────────

SUGGEST_SYSTEM_PROMPT = """You are an expert cybersecurity analyst specialising in the MITRE ATT&CK Enterprise framework.

Given a penetration test finding (title, category, description), identify the most relevant ATT&CK techniques.

Respond with a JSON object of exactly this shape:
{"techniques": [{"technique_id": "T1059.001", "reasoning": "one short sentence"}]}

Guidelines:
- Use Enterprise ATT&CK technique IDs (e.g. T1059, T1059.001). Include sub-techniques where appropriate.
- Return between 0 and 5 techniques. If the finding lacks enough detail to map confidently, return {"techniques": []}.
- Keep each `reasoning` to one short sentence.
"""

# Per-finding timeout for LLM inference (local models can be slow)
AI_REQUEST_TIMEOUT = 300  # 5 minutes per finding
# Max concurrent LLM requests. Local backends like LM Studio queue under the
# hood and share KV cache across concurrent requests on the same model, which
# in practice causes context-window overflow rather than speedup. Keep at 1.
AI_MAX_CONCURRENCY = 1
# Cap finding description length sent to the LLM. Tighter than necessary so
# the system prompt + reasoning headroom comfortably fits in a 4-8k context.
AI_MAX_DESCRIPTION_CHARS = 1200

# OpenAI-compatible structured output schema. Constrains the FINAL answer
# to match this exact shape via grammar-based sampling. Supported by
# LM Studio, vLLM, OpenAI, Ollama (recent), llama.cpp's server.
SUGGEST_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "techniques": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "technique_id": {
                        "type": "string",
                        "description": "Enterprise ATT&CK technique ID, e.g. T1059 or T1059.001",
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "One short sentence on why this technique applies",
                    },
                },
                "required": ["technique_id", "reasoning"],
            },
            "maxItems": 5,
        },
    },
    "required": ["techniques"],
}


def _extract_techniques_from_content(content: str) -> list[dict] | None:
    """
    Extract a list of technique dicts from a model's `content` field.

    Tolerates a wide range of model behaviours so this works model-agnostically
    even when the OpenAI `response_format: json_object` constraint isn't
    available or isn't fully respected:

      • {"techniques": [...]}      — preferred shape requested by the prompt
      • [...]                      — bare array, returned by some models
      • <think>...</think>{...}    — reasoning trace prepended; stripped first
      • ```json\\n{...}\\n```      — markdown-fenced JSON; fences stripped
      • "any prose then {...}"     — last balanced JSON object recovered

    Returns the techniques list on success, [] if the model decided no
    techniques apply, or None if no JSON could be recovered.
    """
    text = content.strip()

    # 1. Strip closed <think>...</think> reasoning blocks.
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    # 2. Strip an unclosed leading <think> trace (truncated thinking output).
    if text.startswith("<think>"):
        cut = text.find("</think>")
        text = text[cut + len("</think>"):] if cut >= 0 else text[len("<think>"):]
        text = text.strip()
    # 3. Strip surrounding markdown code fences.
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        text = text.rsplit("```", 1)[0].strip()

    if not text:
        return None

    # 4. Try parsing as-is — the happy path under response_format=json_object.
    parsed = None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # 5. Recover by finding the outermost balanced JSON object or array.
        for opener, closer in (("{", "}"), ("[", "]")):
            start = text.find(opener)
            end = text.rfind(closer)
            if start >= 0 and end > start:
                try:
                    parsed = json.loads(text[start : end + 1])
                    break
                except json.JSONDecodeError:
                    continue

    if parsed is None:
        return None

    # 6. Normalise to a list of technique dicts. Accept both shapes.
    if isinstance(parsed, dict):
        items = parsed.get("techniques") or parsed.get("results") or []
    elif isinstance(parsed, list):
        items = parsed
    else:
        return None

    if not isinstance(items, list):
        return None

    return [
        {
            "technique_id": str(t.get("technique_id", "")).strip(),
            "reasoning": str(t.get("reasoning", "")).strip(),
        }
        for t in items
        if isinstance(t, dict) and t.get("technique_id")
    ]


async def _suggest_for_finding(
    client: "httpx.AsyncClient",
    finding: Finding,
    api_url: str,
    api_key: str,
    model: str,
    semaphore: "asyncio.Semaphore",
    index: int,
    total: int,
) -> dict:
    """Process a single finding through the LLM. Runs under a semaphore."""
    async with semaphore:
        # Skip API call entirely for findings with no real content — saves a
        # round-trip and avoids the model hallucinating from a one-word title.
        title_text = (finding.title or "").strip()
        desc_text = (finding.description or "").strip()
        if len(title_text) + len(desc_text) < 20:
            return {
                "finding_id": finding.id,
                "finding_title": finding.title,
                "techniques": [],
                "error": "Finding has insufficient detail to map (title and description nearly empty).",
            }

        user_msg = (
            f"Title: {title_text}\n"
            f"Category: {finding.category or 'N/A'}\n"
            f"Description: {desc_text[:AI_MAX_DESCRIPTION_CHARS]}"
        )
        print(f"[ATT&CK Suggest] [{index}/{total}] Calling AI for finding: {finding.title[:60]}")
        try:
            resp = await client.post(
                f"{api_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": SUGGEST_SYSTEM_PROMPT},
                        {"role": "user", "content": user_msg},
                    ],
                    "temperature": 0.2,
                    # max_tokens caps the COMBINED reasoning + final answer
                    # for reasoning models (thinking + content share the same
                    # budget). 8k gives Qwen 3 / o-series / DeepSeek-R1 room
                    # to think for 1-3k tokens then still emit the answer.
                    "max_tokens": 8192,
                    # Constrain the FINAL output to a strict JSON schema via
                    # grammar-based sampling. Reasoning models can still think
                    # (in a separate `reasoning_content` field); only the
                    # `content` field is shape-constrained. Supported by
                    # LM Studio, vLLM, OpenAI, Ollama (recent), llama.cpp.
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "attack_techniques",
                            "strict": True,
                            "schema": SUGGEST_RESPONSE_SCHEMA,
                        },
                    },
                    "stream": False,
                },
            )
            print(f"[ATT&CK Suggest] [{index}/{total}] AI response status: {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                choice = (data.get("choices") or [{}])[0]
                message = choice.get("message", {}) or {}
                finish_reason = choice.get("finish_reason", "")

                # Try multiple sources, in order of how OpenAI-compatible
                # servers commonly surface a structured-output answer:
                #   1. `content` — the canonical place, populated by most
                #      servers when json_schema is honoured cleanly.
                #   2. `tool_calls[*].function.arguments` — some servers
                #      (and OpenAI itself for `type:"function"` calls) put
                #      structured output here as a JSON string.
                #   3. `reasoning_content` — last resort, for models that
                #      emit the JSON as part of their thinking trace.
                candidates: list[tuple[str, str]] = []
                if message.get("content"):
                    candidates.append(("content", message["content"]))
                for tc in (message.get("tool_calls") or []):
                    args = (tc.get("function") or {}).get("arguments")
                    if args:
                        candidates.append(("tool_call", args))
                if message.get("reasoning_content"):
                    candidates.append(("reasoning_content", message["reasoning_content"]))

                techniques: Optional[list[dict]] = None
                source_used = None
                for source, raw in candidates:
                    parsed = _extract_techniques_from_content(raw)
                    if parsed is not None:
                        techniques = parsed
                        source_used = source
                        break

                if techniques is None:
                    msg_keys = list(message.keys())
                    has_reasoning = bool(message.get("reasoning_content"))
                    print(
                        f"[ATT&CK Suggest] [{index}/{total}] No parseable JSON found. "
                        f"finish_reason={finish_reason}, keys={msg_keys}, has_reasoning={has_reasoning}"
                    )
                    if finish_reason == "length":
                        err = (
                            "Model hit max_tokens before producing the answer. "
                            "Raise max_tokens, shrink the input, or use a non-reasoning model."
                        )
                    elif has_reasoning and not message.get("content"):
                        err = (
                            "Model spent all tokens on reasoning and produced no answer. "
                            "Disable thinking mode in LM Studio's load settings, raise max_tokens, "
                            "or use a non-reasoning model."
                        )
                    else:
                        err = "Model returned no parseable JSON in content, tool_calls, or reasoning."
                    return {
                        "finding_id": finding.id,
                        "finding_title": finding.title,
                        "techniques": [],
                        "error": err,
                    }

                preview = next(raw[:300] for src, raw in candidates if src == source_used)
                print(
                    f"[ATT&CK Suggest] [{index}/{total}] Parsed {len(techniques)} techniques "
                    f"from {source_used}. Preview: {preview}"
                )
                return {
                    "finding_id": finding.id,
                    "finding_title": finding.title,
                    "techniques": techniques,
                }
            else:
                resp_text = resp.text[:200]
                print(f"[ATT&CK Suggest] [{index}/{total}] AI API error: {resp.status_code} — {resp_text}")
                # Extract a concise message from the AI backend's JSON body if present
                err_msg = f"AI API returned {resp.status_code}"
                try:
                    body = resp.json()
                    if isinstance(body, dict) and body.get("error"):
                        ai_err = body["error"]
                        err_msg = ai_err if isinstance(ai_err, str) else (ai_err.get("message") or err_msg)
                except Exception:
                    pass
                return {
                    "finding_id": finding.id,
                    "finding_title": finding.title,
                    "techniques": [],
                    "error": err_msg,
                }
        except Exception as e:
            print(f"[ATT&CK Suggest] [{index}/{total}] Exception: {type(e).__name__}: {e}")
            return {
                "finding_id": finding.id,
                "finding_title": finding.title,
                "techniques": [],
                "error": f"{type(e).__name__}: {e}",
            }


@router.post("/engagement/{engagement_id}/suggest")
async def suggest_techniques(
    engagement_id: str,
    request: SuggestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """AI-suggest ATT&CK techniques for unmapped findings."""
    from models.ai_settings import AiSetting
    import asyncio
    import httpx

    print(f"[ATT&CK Suggest] Called for engagement {engagement_id}, finding_ids={request.finding_ids}")

    # Check AI enabled
    ai_result = await db.execute(select(AiSetting))
    settings = {r.key: r.value for r in ai_result.scalars().all()}

    ai_enabled = settings.get("ai_enabled", "false")
    print(f"[ATT&CK Suggest] ai_enabled={ai_enabled}")

    if ai_enabled.lower() != "true":
        print("[ATT&CK Suggest] AI is disabled, returning 403")
        raise HTTPException(403, "AI assistant is disabled")

    api_url = settings.get("ai_api_url", "https://api.openai.com/v1").rstrip("/")
    api_key = settings.get("ai_api_key", "")
    model = settings.get("ai_default_model", "gpt-4o")

    print(f"[ATT&CK Suggest] api_url={api_url}, model={model}, has_key={bool(api_key)}")

    if not api_key:
        print("[ATT&CK Suggest] No API key, returning 400")
        raise HTTPException(400, "AI API key not configured")

    # Fetch findings
    finding_ids = request.finding_ids
    if not finding_ids:
        # Default: all unmapped findings for this engagement
        findings_result = await db.execute(
            select(Finding)
            .where(Finding.engagement_id == engagement_id)
            .options(selectinload(Finding.attack_techniques))
        )
        all_findings = findings_result.scalars().all()
        unmapped = [f for f in all_findings if not f.attack_techniques]
        finding_ids = [f.id for f in unmapped]
        print(f"[ATT&CK Suggest] Found {len(all_findings)} total findings, {len(unmapped)} unmapped")

    if not finding_ids:
        print("[ATT&CK Suggest] No unmapped findings, returning early")
        return {"suggestions": [], "message": "All findings already have techniques mapped"}

    # Fetch the actual finding data
    findings_result = await db.execute(
        select(Finding).where(Finding.id.in_(finding_ids))
    )
    findings = findings_result.scalars().all()
    print(f"[ATT&CK Suggest] Processing {len(findings)} findings concurrently (max {AI_MAX_CONCURRENCY})")

    # Process findings concurrently with bounded concurrency
    semaphore = asyncio.Semaphore(AI_MAX_CONCURRENCY)
    async with httpx.AsyncClient(timeout=AI_REQUEST_TIMEOUT) as client:
        tasks = [
            _suggest_for_finding(
                client, f, api_url, api_key, model,
                semaphore, i + 1, len(findings),
            )
            for i, f in enumerate(findings)
        ]
        suggestions = await asyncio.gather(*tasks)

    suggestions = list(suggestions)
    succeeded = sum(1 for s in suggestions if s.get("techniques"))
    failed = sum(1 for s in suggestions if s.get("error"))
    # First non-empty error string for the toast
    first_error = next((s.get("error") for s in suggestions if s.get("error")), None)
    print(
        f"[ATT&CK Suggest] Done — {succeeded}/{len(suggestions)} succeeded, "
        f"{failed} failed. first_error={first_error}"
    )
    return {
        "suggestions": suggestions,
        "succeeded": succeeded,
        "failed": failed,
        "first_error": first_error,
    }


# ── Navigator Export ──────────────────────────────────────────────────

@router.get("/engagement/{engagement_id}/navigator")
async def export_navigator_json(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export ATT&CK Navigator JSON layer for an engagement.

    Generates a valid ATT&CK Navigator layer file that can be imported
    into https://mitre-attack.github.io/attack-navigator/
    """
    from models.engagement import Engagement

    eng_result = await db.execute(
        select(Engagement).where(Engagement.id == engagement_id)
    )
    engagement = eng_result.scalar_one_or_none()
    if not engagement:
        raise HTTPException(404, "Engagement not found")

    # Fetch coverage data
    findings_result = await db.execute(
        select(Finding)
        .where(Finding.engagement_id == engagement_id)
        .options(selectinload(Finding.attack_techniques))
    )
    findings = findings_result.scalars().all()

    # Build technique counts and severity-based scoring
    technique_counts: dict[str, int] = {}
    technique_severities: dict[str, list[str]] = {}

    severity_score = {
        "CRITICAL": 5,
        "HIGH": 4,
        "MEDIUM": 3,
        "LOW": 2,
        "INFO": 1,
    }

    for f in findings:
        sev = f.severity.value if f.severity else "INFO"
        for at in (f.attack_techniques or []):
            tid = at.technique_id
            technique_counts[tid] = technique_counts.get(tid, 0) + 1
            technique_severities.setdefault(tid, []).append(sev)

    # Build Navigator techniques array
    nav_techniques = []
    for tid, count in technique_counts.items():
        sevs = technique_severities.get(tid, [])
        max_sev = max((severity_score.get(s, 0) for s in sevs), default=0)
        # Color gradient based on max severity
        color_map = {
            5: "#ff0000",  # Critical - red
            4: "#ff6600",  # High   - orange
            3: "#ffaa00",  # Medium - amber
            2: "#3b82f6",  # Low    - blue
            1: "#94a3b8",  # Info   - slate
        }
        color = color_map.get(max_sev, "#94a3b8")

        # Handle sub-techniques: technique_id like T1059.001
        base_tid = tid
        tactic = ""
        if "." in tid:
            base_tid = tid  # Navigator uses full ID for sub-techniques

        nav_techniques.append({
            "techniqueID": tid,
            "score": max_sev,
            "color": color,
            "comment": f"{count} finding{'s' if count != 1 else ''}: max severity {sevs[0] if len(set(sevs)) == 1 else 'mixed'}",
            "enabled": True,
            "showSubtechniques": False,
        })

    # Build the Navigator layer JSON
    layer = {
        "name": f"RedWire: {engagement.name}",
        "versions": {
            "attack": "16",
            "navigator": "5.1.0",
            "layer": "4.5",
        },
        "domain": "enterprise-attack",
        "description": f"ATT&CK coverage for engagement '{engagement.name}' — exported from RedWire",
        "filters": {
            "platforms": [
                "Linux", "macOS", "Windows", "Network",
                "PRE", "Containers", "Office 365", "SaaS",
                "Google Workspace", "IaaS", "Azure AD"
            ]
        },
        "sorting": 3,  # Sort by score descending
        "layout": {
            "layout": "side",
            "aggregateFunction": "average",
            "showID": True,
            "showName": True,
            "showAggregateScores": False,
            "countUnscored": False,
        },
        "hideDisabled": False,
        "techniques": nav_techniques,
        "gradient": {
            "colors": ["#ffffff", "#ff6666"],
            "minValue": 0,
            "maxValue": 5,
        },
        "legendItems": [
            {"label": "Critical", "color": "#ff0000"},
            {"label": "High", "color": "#ff6600"},
            {"label": "Medium", "color": "#ffaa00"},
            {"label": "Low", "color": "#3b82f6"},
            {"label": "Info", "color": "#94a3b8"},
        ],
        "showTacticRowBackground": True,
        "tacticRowBackground": "#1e293b",
        "selectTechniquesAcrossTactics": True,
        "selectSubtechniquesWithParent": False,
        "selectVisibleTechniques": False,
        "metadata": [
            {"name": "platform", "value": "RedWire"},
            {"name": "engagement_id", "value": engagement_id},
        ],
    }

    # Return as downloadable JSON
    content = json.dumps(layer, indent=2)
    filename = f"redwire_attack_{engagement.name.replace(' ', '_').lower()}.json"

    return JSONResponse(
        content=layer,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
