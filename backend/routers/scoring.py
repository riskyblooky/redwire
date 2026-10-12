"""Scoring-model API — lists the available rating models and (optionally)
evaluates one server-side.

The frontend calculator renders inputs from a model definition and computes the
score client-side; the same engine runs on write for authoritative persistence
(see routers/findings.py::_apply_scoring). This router exposes the model
catalog that both sides read.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from database import get_db
from models.user import User
from scoring.engine import ScoringError, evaluate as evaluate_score
from scoring.registry import DEFAULT_MODEL_ID, scoring_registry
from scoring.types import ScoreResult, ScoringModel
from utils.scoring_policy import get_effective_policy

router = APIRouter(prefix="/scoring", tags=["scoring"])


class ScoringModelSummary(BaseModel):
    id: str
    label: str
    version: str
    source: str
    score_kind: str
    description: str | None = None


@router.get("/models", response_model=List[ScoringModelSummary])
async def list_scoring_models(current_user: User = Depends(get_current_user)):
    """List the available scoring models (summary form, for the picker)."""
    return [
        ScoringModelSummary(
            id=m.id, label=m.label, version=m.version, source=m.source,
            score_kind=m.score_kind, description=m.description,
        )
        for m in scoring_registry.list()
    ]


@router.get("/models/{model_id}", response_model=ScoringModel)
async def get_scoring_model(model_id: str, current_user: User = Depends(get_current_user)):
    """Full definition of one model (metrics + formula + severity mapping) so the
    calculator can render and evaluate it."""
    model = scoring_registry.get(model_id)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Unknown scoring model '{model_id}'")
    return model


@router.get("/default", response_model=ScoringModelSummary)
async def get_default_model(current_user: User = Depends(get_current_user)):
    """The default scoring model for new findings."""
    model = scoring_registry.get(DEFAULT_MODEL_ID) or (scoring_registry.list() or [None])[0]
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No scoring models available")
    return ScoringModelSummary(
        id=model.id, label=model.label, version=model.version, source=model.source,
        score_kind=model.score_kind, description=model.description,
    )


class EffectivePolicyResponse(BaseModel):
    allowed: List[ScoringModelSummary]
    default: str
    locked: bool


@router.get("/effective-policy", response_model=EffectivePolicyResponse)
async def effective_policy(
    engagement_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The scoring models permitted for an engagement (site policy resolved with
    the engagement's own policy), the default to preselect, and whether the model
    is locked (a single model — the picker should disable switching)."""
    eff = await get_effective_policy(db, engagement_id)
    by_id = {m.id: m for m in scoring_registry.list()}
    allowed = [
        ScoringModelSummary(
            id=m.id, label=m.label, version=m.version, source=m.source,
            score_kind=m.score_kind, description=m.description,
        )
        for mid in eff["allowed"] if (m := by_id.get(mid)) is not None
    ]
    return EffectivePolicyResponse(allowed=allowed, default=eff["default"], locked=eff["locked"])


class EvaluateRequest(BaseModel):
    model_id: str
    inputs: Dict[str, Any]


@router.post("/evaluate", response_model=ScoreResult)
async def evaluate_scoring(req: EvaluateRequest, current_user: User = Depends(get_current_user)):
    """Evaluate a model over inputs server-side (parity check / headless clients).
    The UI normally computes client-side with the same engine."""
    model = scoring_registry.get(req.model_id)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Unknown scoring model '{req.model_id}'")
    try:
        return evaluate_score(model, req.inputs)
    except ScoringError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
