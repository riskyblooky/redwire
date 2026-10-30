"""Presentation helpers shared by the API and report generation."""

from __future__ import annotations

from typing import Any, Dict, Optional

from scoring.engine import ScoringError, evaluate
from scoring.registry import scoring_registry


def outcome_label(model_id: Optional[str], inputs: Optional[Dict[str, Any]]) -> Optional[str]:
    """Display label for a categorical model's outcome (e.g. "Extremely High").

    Returns None for numeric models — their ``cvss_score`` is the real score —
    and whenever the outcome can't be recomputed (no inputs, unknown model).
    Categorical models store only a nominal ``cvss_score`` for sorting, so the
    outcome is re-derived from the persisted ``score_inputs``.
    """
    if not model_id or not inputs:
        return None
    model = scoring_registry.get(model_id)
    if model is None or model.score_kind != "categorical":
        return None
    try:
        token = evaluate(model, inputs).outcome
    except ScoringError:
        return None
    if not token:
        return None
    return (model.outcome_labels or {}).get(token) or token.title()
