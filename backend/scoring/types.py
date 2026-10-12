"""Pydantic definitions for scoring models and results.

A ``ScoringModel`` is loaded from JSON (built-in ``scoring/models/*.json`` or a
plugin). ``ScoreResult`` is the single shape the rest of RedWire consumes.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class MetricOption(BaseModel):
    """One choice for a ``select`` metric. ``weight`` feeds numeric formulas;
    ``value`` is the categorical token used by matrix/lookup formulas."""

    value: str
    label: str
    weight: Optional[float] = None
    description: Optional[str] = None


class Metric(BaseModel):
    """A calculator input. ``select`` renders a dropdown of ``options``;
    ``number`` renders a bounded numeric input."""

    id: str
    label: str
    group: Optional[str] = None
    type: Literal["select", "number"]
    options: Optional[List[MetricOption]] = None
    min: Optional[float] = None
    max: Optional[float] = None
    description: Optional[str] = None


class SeverityMapping(BaseModel):
    """How a formula result becomes a Severity. ``bands`` for numeric results,
    ``map`` for categorical outcomes."""

    model_config = ConfigDict(populate_by_name=True)

    from_: Literal["bands", "map"] = Field(default="bands", alias="from")
    bands: Optional[List[Dict[str, Any]]] = None
    map: Optional[Dict[str, str]] = None


class ScoringModel(BaseModel):
    """A full, self-describing rating model."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    label: str
    version: str = "1.0"
    source: str = "builtin"  # "builtin" | "plugin:<id>"
    score_kind: Literal["numeric", "categorical"] = "numeric"
    description: Optional[str] = None

    metrics: List[Metric]
    formula: Dict[str, Any]
    severity: SeverityMapping

    vector_template: Optional[str] = None
    # Nominal 0-10 score per severity, so categorical models still sort among
    # numeric ones. Only used when a formula yields no real number.
    nominal_score: Optional[Dict[str, float]] = None

    def metric(self, metric_id: str) -> Optional[Metric]:
        for m in self.metrics:
            if m.id == metric_id:
                return m
        return None


class ScoreResult(BaseModel):
    """The output every model produces. ``severity`` is always set and always a
    member of the existing enum — that is what keeps downstream code unchanged."""

    model_id: str
    score: Optional[float] = None       # -> Finding.cvss_score
    outcome: Optional[str] = None       # categorical label, e.g. "Act"
    severity: str                       # -> Finding.severity (enum value)
    vector: Optional[str] = None        # -> Finding.cvss_vector (opaque string)
    inputs: Dict[str, Any] = Field(default_factory=dict)
