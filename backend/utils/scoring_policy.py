"""Scoring-model policy — which scoring models may be used, site-wide and
per-engagement.

Site-wide policy lives in the AuthSetting KV table (same pattern as
peer_review / stats-scope):
  - SCORING_ENABLED_MODELS  JSON list of model ids, or unset = all available
  - SCORING_DEFAULT_MODEL   model id, or unset = "cvss31"/first
  - SCORING_LOCKED_MODEL    model id — forces this one model everywhere, or unset

Per-engagement policy lives on the Engagement row:
  - allowed_score_models  JSON list of model ids, or null = inherit site
  - default_score_model   model id, or null = inherit site

The *effective* policy for an engagement resolves these together (see
resolve_effective). The picker shows only the allowed models and locks when a
single model is allowed; the backend enforces the allowed set on finding save.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

ENABLED_KEY = "SCORING_ENABLED_MODELS"
DEFAULT_KEY = "SCORING_DEFAULT_MODEL"
LOCKED_KEY = "SCORING_LOCKED_MODEL"

_FALLBACK_DEFAULT = "cvss31"


def _parse_list(raw: Optional[str]) -> Optional[List[str]]:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        v = json.loads(s)
        if isinstance(v, list):
            out = [str(x).strip() for x in v if str(x).strip()]
            return out or None
    except (ValueError, TypeError):
        pass
    out = [x.strip() for x in s.split(",") if x.strip()]
    return out or None


async def get_site_policy(db: AsyncSession) -> Dict[str, Any]:
    """Return {enabled_models: [ids]|None, default_model: id|None, locked_model: id|None}."""
    from models.auth_settings import AuthSetting
    rows = (await db.execute(
        select(AuthSetting).where(AuthSetting.key.in_([ENABLED_KEY, DEFAULT_KEY, LOCKED_KEY]))
    )).scalars().all()
    vals = {r.key: (r.value or "") for r in rows}
    return {
        "enabled_models": _parse_list(vals.get(ENABLED_KEY)),
        "default_model": (vals.get(DEFAULT_KEY) or "").strip() or None,
        "locked_model": (vals.get(LOCKED_KEY) or "").strip() or None,
    }


async def set_site_policy(db: AsyncSession, *, enabled_models, default_model, locked_model, user_id: Optional[str]) -> None:
    from models.auth_settings import AuthSetting

    async def _set(key: str, value: str) -> None:
        row = (await db.execute(select(AuthSetting).where(AuthSetting.key == key))).scalar_one_or_none()
        if row is None:
            row = AuthSetting(key=key, value=value, is_encrypted=False)
            db.add(row)
        else:
            row.value = value
        row.updated_by = user_id

    await _set(ENABLED_KEY, json.dumps(enabled_models) if enabled_models else "")
    await _set(DEFAULT_KEY, (default_model or "").strip())
    await _set(LOCKED_KEY, (locked_model or "").strip())
    await db.commit()


def resolve_effective(
    site: Dict[str, Any],
    eng_allowed: Optional[List[str]],
    eng_default: Optional[str],
    available_ids: List[str],
) -> Dict[str, Any]:
    """Resolve the effective policy. Returns {allowed: [ids], default: id, locked: bool}.

    `locked` means the picker should not let the user switch models (true when a
    single model is allowed — including the site-wide forced model)."""
    available = list(available_ids)
    avail = set(available)

    site_enabled = site.get("enabled_models")
    enabled = [m for m in site_enabled if m in avail] if site_enabled else list(available)
    if not enabled:
        enabled = list(available)

    locked_model = site.get("locked_model")
    if locked_model and locked_model in avail:
        return {"allowed": [locked_model], "default": locked_model, "locked": True}

    enabled_set = set(enabled)
    if eng_allowed:
        allowed = [m for m in eng_allowed if m in enabled_set]
        if not allowed:
            allowed = enabled
    else:
        allowed = enabled

    allowed_set = set(allowed)
    default = next(
        (c for c in (eng_default, site.get("default_model"), _FALLBACK_DEFAULT) if c and c in allowed_set),
        allowed[0] if allowed else _FALLBACK_DEFAULT,
    )
    return {"allowed": allowed, "default": default, "locked": len(allowed) == 1}


async def get_effective_policy(db: AsyncSession, engagement_id: Optional[str]) -> Dict[str, Any]:
    from scoring.registry import scoring_registry
    eng_allowed = eng_default = None
    if engagement_id:
        from models.engagement import Engagement
        eng = (await db.execute(
            select(Engagement).where(Engagement.id == engagement_id)
        )).scalar_one_or_none()
        if eng is not None:
            eng_allowed = eng.allowed_score_models
            eng_default = eng.default_score_model
    site = await get_site_policy(db)
    return resolve_effective(site, eng_allowed, eng_default, scoring_registry.ids())


async def assert_engagement_policy_allowed(
    db: AsyncSession,
    allowed_models: Optional[List[str]],
    default_model: Optional[str],
    prev_allowed: Optional[List[str]] = None,
    prev_default: Optional[str] = None,
) -> None:
    """Raise 422 if an engagement's scoring policy adds a model the site policy
    doesn't permit. Ids the engagement already had are left alone, so a site
    narrowing later doesn't block unrelated engagement edits (resolve_effective
    ignores them anyway)."""
    site_allowed = set((await get_effective_policy(db, None))["allowed"])
    prev = set(prev_allowed or [])
    bad = [m for m in (allowed_models or []) if m not in site_allowed and m not in prev]
    if default_model and default_model != prev_default and default_model not in site_allowed:
        bad.append(default_model)
    if bad:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Scoring model(s) {', '.join(sorted(set(bad)))} are not enabled site-wide. "
                f"Enabled: {', '.join(sorted(site_allowed)) or '(none)'}."
            ),
        )


async def assert_model_allowed(db: AsyncSession, engagement_id: Optional[str], model_id: str) -> None:
    """Raise 422 if model_id is not permitted for this engagement's effective policy."""
    eff = await get_effective_policy(db, engagement_id)
    if model_id not in eff["allowed"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Scoring model '{model_id}' is not permitted for this engagement. "
                f"Allowed: {', '.join(eff['allowed']) or '(none)'}."
            ),
        )
