"""CVSS v3.1 base-score engine (server-side).

Python port of FIRST.ORG's cvsscalc31.js (BSD-3-Clause), matching the frontend
``frontend/src/lib/cvss31.ts`` exactly so client preview and server authority
never diverge.
"""

from __future__ import annotations

import math
from typing import Dict, Tuple

_WEIGHT: Dict[str, Dict] = {
    "AV": {"N": 0.85, "A": 0.62, "L": 0.55, "P": 0.2},
    "AC": {"H": 0.44, "L": 0.77},
    "PR": {
        "U": {"N": 0.85, "L": 0.62, "H": 0.27},  # Scope Unchanged
        "C": {"N": 0.85, "L": 0.68, "H": 0.50},  # Scope Changed
    },
    "UI": {"N": 0.85, "R": 0.62},
    "S": {"U": 6.42, "C": 7.52},
    "CIA": {"N": 0.0, "L": 0.22, "H": 0.56},
}

_EXPLOITABILITY_COEFFICIENT = 8.22
_SCOPE_COEFFICIENT = 1.08

_BASE_METRICS = ["AV", "AC", "PR", "UI", "S", "C", "I", "A"]


def _round_up1(value: float) -> float:
    """CVSS 3.1 spec rounding: round up to one decimal place."""
    int_input = round(value * 100000)
    if int_input % 10000 == 0:
        return int_input / 100000
    return (math.floor(int_input / 10000) + 1) / 10.0


def calculate_from_metrics(metrics: Dict[str, str]) -> Tuple[float, str]:
    """Compute (base_score, vector_string) from the 8 base metrics.

    Raises ValueError with a descriptive message for missing or unknown values.
    """
    missing = [k for k in _BASE_METRICS if not metrics.get(k)]
    if missing:
        raise ValueError(f"CVSS 3.1 missing base metric(s): {', '.join(missing)}")

    av, ac, pr, ui, s, c, i, a = (metrics[k] for k in _BASE_METRICS)

    bad = []
    if av not in _WEIGHT["AV"]:
        bad.append("AV")
    if ac not in _WEIGHT["AC"]:
        bad.append("AC")
    if s not in _WEIGHT["PR"] or pr not in _WEIGHT["PR"].get(s, {}):
        bad.append("PR" if s in _WEIGHT["PR"] else "S")
    if ui not in _WEIGHT["UI"]:
        bad.append("UI")
    if s not in _WEIGHT["S"]:
        bad.append("S")
    for key, val in (("C", c), ("I", i), ("A", a)):
        if val not in _WEIGHT["CIA"]:
            bad.append(key)
    if bad:
        raise ValueError(f"CVSS 3.1 unknown metric value(s): {', '.join(sorted(set(bad)))}")

    w_av = _WEIGHT["AV"][av]
    w_ac = _WEIGHT["AC"][ac]
    w_pr = _WEIGHT["PR"][s][pr]  # PR weight depends on Scope
    w_ui = _WEIGHT["UI"][ui]
    w_s = _WEIGHT["S"][s]
    w_c = _WEIGHT["CIA"][c]
    w_i = _WEIGHT["CIA"][i]
    w_a = _WEIGHT["CIA"][a]

    iss = 1 - ((1 - w_c) * (1 - w_i) * (1 - w_a))

    if s == "U":
        impact = w_s * iss
    else:
        impact = w_s * (iss - 0.029) - 3.25 * math.pow(iss - 0.02, 15)

    exploitability = _EXPLOITABILITY_COEFFICIENT * w_av * w_ac * w_pr * w_ui

    if impact <= 0:
        base_score = 0.0
    elif s == "U":
        base_score = _round_up1(min(exploitability + impact, 10))
    else:
        base_score = _round_up1(min(_SCOPE_COEFFICIENT * (exploitability + impact), 10))

    vector = f"CVSS:3.1/AV:{av}/AC:{ac}/PR:{pr}/UI:{ui}/S:{s}/C:{c}/I:{i}/A:{a}"
    return base_score, vector
