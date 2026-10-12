"""Pluggable finding-scoring engine.

Scoring models are data (``ScoringModel`` JSON) interpreted by a small set of
safe formula primitives. Every model — built-in or plugin-contributed — produces
a :class:`ScoreResult` whose ``severity`` lands in the existing 5-value
``Severity`` enum, so all downstream consumers (analytics, dashboards, reports,
automation, MCP, scan importers) keep working unchanged.

See ``docs/pluggable-finding-scoring.md`` for the full design.
"""

from scoring.types import (
    Metric,
    MetricOption,
    ScoringModel,
    ScoreResult,
    SeverityMapping,
)
from scoring.engine import ScoringError, evaluate
from scoring.registry import ScoringRegistry, scoring_registry
from scoring.severity import DEFAULT_BANDS, score_to_severity

__all__ = [
    "Metric",
    "MetricOption",
    "ScoringModel",
    "ScoreResult",
    "SeverityMapping",
    "ScoringError",
    "evaluate",
    "ScoringRegistry",
    "scoring_registry",
    "DEFAULT_BANDS",
    "score_to_severity",
]
