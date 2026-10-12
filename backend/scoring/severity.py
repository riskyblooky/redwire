"""Canonical score/outcome -> severity mapping.

This is the ONE place the backend turns a numeric score into a severity level.
Before the scoring engine this logic did not exist server-side at all (severity
was free-form from the client); the frontend duplicated a CVSS band table in
~6 spots. New code must go through here.

The scoring package stays decoupled from the ORM: severities are handled here as
validated UPPERCASE strings (the exact members of ``models.finding.Severity``).
Callers at the DB boundary coerce the string into the enum.
"""

from __future__ import annotations

from typing import Iterable, List, Optional, Tuple

# The five members of models.finding.Severity, worst-first. Kept as strings so
# the scoring engine has no ORM / DB import dependency (and is unit-testable).
SEVERITY_ORDER: List[str] = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
VALID_SEVERITIES = set(SEVERITY_ORDER)

# Numeric rank for sorting (higher == more severe).
SEVERITY_RANK = {"CRITICAL": 5, "HIGH": 4, "MEDIUM": 3, "LOW": 2, "INFO": 1}

# Canonical dark-theme hex palette (mirrors the `theme` skill + report defaults).
SEVERITY_COLORS = {
    "CRITICAL": "#ef4444",  # red-500
    "HIGH": "#f97316",      # orange-500
    "MEDIUM": "#eab308",    # yellow-500
    "LOW": "#60a5fa",       # blue-400
    "INFO": "#94a3b8",      # slate-400
}

_ALIASES = {"NONE": "INFO", "INFORMATIONAL": "INFO", "INFORMATION": "INFO"}

# Default 0-10 band table (the CVSS 3.1 / FIRST.ORG bands). Each tuple is an
# inclusive upper bound and the severity for scores up to that bound.
DEFAULT_BANDS: List[Tuple[float, str]] = [
    (0.0, "INFO"),
    (3.9, "LOW"),
    (6.9, "MEDIUM"),
    (8.9, "HIGH"),
    (10.0, "CRITICAL"),
]


def coerce_severity(value) -> str:
    """Accept a Severity enum, or a case-insensitive string/label; return a
    canonical UPPERCASE severity string. Raises ValueError if unrecognized."""
    if value is None:
        raise ValueError("severity value is required")
    text = getattr(value, "value", value)  # unwrap an enum if one was passed
    text = str(text).strip().upper()
    text = _ALIASES.get(text, text)
    if text not in VALID_SEVERITIES:
        raise ValueError(f"unknown severity {value!r}")
    return text


def normalize_bands(bands: Optional[Iterable]) -> List[Tuple[float, str]]:
    """Normalize a model's band list (``[{"max": .., "severity": ..}]`` or
    ``[(max, severity)]``) into sorted ``(max, severity)`` tuples."""
    if not bands:
        return list(DEFAULT_BANDS)
    out: List[Tuple[float, str]] = []
    for b in bands:
        if isinstance(b, dict):
            out.append((float(b["max"]), coerce_severity(b["severity"])))
        else:
            out.append((float(b[0]), coerce_severity(b[1])))
    out.sort(key=lambda t: t[0])
    return out


def score_to_severity(score: Optional[float], bands: Optional[Iterable] = None) -> str:
    """Map a numeric score to a severity string using ``bands`` (defaults to the
    CVSS bands). A null/absent score maps to INFO; scores above the top band
    clamp to the most-severe band."""
    table = normalize_bands(bands)
    if score is None:
        return "INFO"
    val = float(score)
    for upper, sev in table:
        if val <= upper:
            return sev
    return table[-1][1]
