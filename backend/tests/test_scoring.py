"""Pluggable finding scoring — engine, built-in models, CVSS 4.0 plugin,
policy resolution, and report/API display helpers.

Pure-unit: no database. Reference values are the published scores for each
vector (FIRST.org calculators for CVSS 3.1 / 4.0, the AFI 90-802 risk matrix
for the USAF RAC model).
"""

from __future__ import annotations

import json
import os
from types import SimpleNamespace

import pytest

from scoring.display import outcome_label
from scoring.engine import ScoringError, evaluate
from scoring.providers import scoring_provider_registry
from scoring.registry import scoring_registry
from scoring.types import ScoringModel
from utils.scoring_policy import resolve_effective


BUILTIN_IDS = {"cvss31", "dread", "owasp-rr", "usaf-rac"}
_PLUGIN_DIR = os.path.join(os.path.dirname(__file__), "..", "plugins", "cvss4_scoring")


def _metrics(vector: str) -> dict:
    """'AV:N/AC:L/...' -> {'AV': 'N', 'AC': 'L', ...}"""
    return dict(part.split(":") for part in vector.split("/"))


def _model(**overrides) -> ScoringModel:
    """A minimal numeric model with two 0-10 number metrics (a, b)."""
    data = {
        "id": "t",
        "label": "Test",
        "metrics": [
            {"id": "a", "label": "A", "type": "number", "min": 0, "max": 10},
            {"id": "b", "label": "B", "type": "number", "min": 0, "max": 10},
        ],
        "formula": {"op": "average", "of": ["a", "b"]},
        "severity": {"from": "bands"},
    }
    data.update(overrides)
    return ScoringModel.model_validate(data)


# ── registry ─────────────────────────────────────────────────────────


def test_builtin_models_load():
    ids = {m.id for m in scoring_registry.list() if m.source == "builtin"}
    assert BUILTIN_IDS <= ids


# ── CVSS 3.1 (built-in engine) ───────────────────────────────────────


@pytest.mark.parametrize("vector,score,severity", [
    ("AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H", 9.8, "CRITICAL"),
    ("AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H", 10.0, "CRITICAL"),
    ("AV:L/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H", 7.8, "HIGH"),
    ("AV:N/AC:L/PR:N/UI:R/S:C/C:L/I:L/A:N", 6.1, "MEDIUM"),
    ("AV:N/AC:L/PR:L/UI:N/S:U/C:L/I:L/A:N", 5.4, "MEDIUM"),
    ("AV:N/AC:H/PR:N/UI:R/S:U/C:L/I:N/A:N", 3.1, "LOW"),
    ("AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:N", 0.0, "INFO"),
])
def test_cvss31_reference_vectors(vector, score, severity):
    result = evaluate(scoring_registry.require("cvss31"), _metrics(vector))
    assert result.score == score
    assert result.severity == severity
    assert result.vector == f"CVSS:3.1/{vector}"


def test_cvss31_incomplete_vector_rejected():
    with pytest.raises(ScoringError):
        evaluate(scoring_registry.require("cvss31"), {"AV": "N"})


# ── CVSS 4.0 (plugin engine via the provider contract) ───────────────


@pytest.fixture
def cvss40_model():
    from plugins.cvss4_scoring.cvss4_engine import calculate

    scoring_provider_registry.register("cvss40", lambda inputs: calculate(inputs), plugin_id="test")
    with open(os.path.join(_PLUGIN_DIR, "models", "cvss40.json"), encoding="utf-8") as fh:
        model = ScoringModel.model_validate(json.load(fh))
    yield model
    scoring_provider_registry.unregister("cvss40")


@pytest.mark.parametrize("vector,score", [
    ("AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N", 9.3),
    ("AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:H/SI:H/SA:H", 10.0),
    ("AV:N/AC:L/AT:N/PR:L/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N", 8.7),
    ("AV:L/AC:L/AT:N/PR:L/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N", 8.5),
    ("AV:N/AC:L/AT:N/PR:N/UI:N/VC:L/VI:N/VA:N/SC:N/SI:N/SA:N", 6.9),
    ("AV:N/AC:L/AT:N/PR:N/UI:N/VC:N/VI:N/VA:N/SC:N/SI:N/SA:N", 0.0),
])
def test_cvss40_reference_vectors(cvss40_model, vector, score):
    result = evaluate(cvss40_model, _metrics(vector))
    assert result.score == score
    assert result.vector == f"CVSS:4.0/{vector}"


def test_unregistered_engine_is_a_scoring_error(cvss40_model):
    scoring_provider_registry.unregister("cvss40")
    with pytest.raises(ScoringError, match="no provider"):
        evaluate(cvss40_model, _metrics("AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N"))


# ── USAF Risk Assessment Matrix (categorical) ────────────────────────

_PROBS = ["frequent", "likely", "occasional", "seldom", "rarely"]
# AFI 90-802 risk assessment matrix: severity rows × probability columns.
_USAF_MATRIX = {
    "catastrophic": ["EH", "EH", "H", "H", "M"],
    "critical":     ["EH", "H", "H", "M", "L"],
    "moderate":     ["H", "M", "M", "L", "L"],
    "negligible":   ["M", "L", "L", "L", "L"],
}
_USAF_SEVERITY = {"EH": "CRITICAL", "H": "HIGH", "M": "MEDIUM", "L": "LOW"}
_USAF_LABEL = {"EH": "Extremely High", "H": "High", "M": "Medium", "L": "Low"}


@pytest.mark.parametrize("sev,prob,token", [
    (sev, prob, row[i]) for sev, row in _USAF_MATRIX.items() for i, prob in enumerate(_PROBS)
])
def test_usaf_rac_matrix(sev, prob, token):
    model = scoring_registry.require("usaf-rac")
    result = evaluate(model, {"sev": sev, "prob": prob})
    assert result.outcome == token
    assert result.severity == _USAF_SEVERITY[token]
    # Categorical: the score is only the nominal sort key for the severity.
    assert result.score == model.nominal_score[result.severity]
    assert result.vector == f"USAF-RAC/S:{sev}/P:{prob}"
    assert outcome_label("usaf-rac", {"sev": sev, "prob": prob}) == _USAF_LABEL[token]


# ── DREAD / OWASP ────────────────────────────────────────────────────


@pytest.mark.parametrize("value,severity", [(0, "INFO"), (3, "LOW"), (5, "MEDIUM"), (8, "HIGH"), (10, "CRITICAL")])
def test_dread_average_bands(value, severity):
    inputs = {k: value for k in ("D", "R", "E", "A", "Di")}
    result = evaluate(scoring_registry.require("dread"), inputs)
    assert result.score == float(value)
    assert result.severity == severity


def test_dread_missing_factor_rejected():
    with pytest.raises(ScoringError, match="missing value"):
        evaluate(scoring_registry.require("dread"), {"D": 5, "R": 5, "E": 5, "A": 5})


def _owasp_inputs(likelihood: float, impact: float) -> dict:
    model = scoring_registry.require("owasp-rr")
    like_ids = model.formula["steps"][0]["of"]
    imp_ids = model.formula["steps"][1]["of"]
    return {**{m: likelihood for m in like_ids}, **{m: impact for m in imp_ids}}


@pytest.mark.parametrize("likelihood,impact,severity", [
    (1, 1, "INFO"), (1, 4, "LOW"), (1, 8, "MEDIUM"),
    (4, 4, "MEDIUM"), (4, 8, "HIGH"), (8, 1, "MEDIUM"), (8, 8, "CRITICAL"),
])
def test_owasp_risk_matrix(likelihood, impact, severity):
    result = evaluate(scoring_registry.require("owasp-rr"), _owasp_inputs(likelihood, impact))
    assert result.severity == severity
    assert result.outcome == severity


def test_vector_renders_whole_floats_as_ints():
    result = evaluate(scoring_registry.require("owasp-rr"), _owasp_inputs(9.0, 9.0))
    assert result.vector == "OWASP/L:99999999/I:99999999"


# ── engine primitives ────────────────────────────────────────────────


@pytest.mark.parametrize("formula,expected", [
    ({"op": "average", "of": ["a", "b"]}, 5.0),
    ({"op": "weighted_sum", "of": [{"metric": "a", "weight": 3}, {"metric": "b", "weight": 1}]}, 14.0),
    ({"op": "weighted_sum", "normalize": True,
      "of": [{"metric": "a", "weight": 3}, {"metric": "b", "weight": 1}]}, 3.5),
    ({"op": "product", "of": ["a", "b"]}, 16.0),
    ({"op": "max", "of": ["a", "b"]}, 8.0),
    ({"op": "min", "of": ["a", "b"]}, 2.0),
    ({"op": "average", "of": ["a", "b"], "scale": {"from": [0, 10], "to": [0, 5]}}, 2.5),
    ({"op": "pipeline", "steps": [{"id": "s", "op": "max", "of": ["a", "b"]},
                                  {"id": "o", "op": "product", "of": ["$s", 0.5]}],
      "output": "o"}, 4.0),
])
def test_numeric_primitives(formula, expected):
    result = evaluate(_model(formula=formula), {"a": 2, "b": 8})
    assert result.score == expected


def test_bucket_and_lookup_table_produce_outcomes():
    formula = {"op": "pipeline", "steps": [
        {"id": "ba", "op": "bucket", "of": "a", "bands": [{"max": 5, "label": "lo"}, {"max": 10, "label": "hi"}]},
        {"id": "bb", "op": "bucket", "of": "b", "bands": [{"max": 5, "label": "lo"}, {"max": 10, "label": "hi"}]},
        {"id": "out", "op": "lookup_table", "keys": ["$ba", "$bb"],
         "table": {"lo|lo": "OK", "lo|hi": "WARN", "hi|lo": "WARN", "hi|hi": "BAD"}},
    ], "output": "out"}
    model = _model(formula=formula, score_kind="categorical",
                   severity={"from": "map", "map": {"OK": "LOW", "WARN": "MEDIUM", "BAD": "HIGH"}})
    assert evaluate(model, {"a": 2, "b": 8}).severity == "MEDIUM"
    assert evaluate(model, {"a": 9, "b": 8}).outcome == "BAD"


@pytest.mark.parametrize("formula,inputs,match", [
    ({"op": "nope"}, {"a": 1, "b": 1}, "unknown formula op"),
    ({"op": "average", "of": ["a", "b"]}, {"a": "x", "b": 1}, "not a number"),
    ({"op": "max", "of": []}, {"a": 1, "b": 1}, "at least one"),
])
def test_engine_errors(formula, inputs, match):
    with pytest.raises(ScoringError, match=match):
        evaluate(_model(formula=formula), inputs)


def test_unmapped_categorical_outcome_rejected():
    model = _model(formula={"op": "bucket", "of": "a", "bands": [{"max": 10, "label": "X"}]},
                   score_kind="categorical", severity={"from": "map", "map": {"Y": "LOW"}})
    with pytest.raises(ScoringError, match="no severity mapping"):
        evaluate(model, {"a": 1, "b": 1})


# ── outcome_label (API score_outcome) ────────────────────────────────


def test_outcome_label_none_for_numeric_and_unscored():
    assert outcome_label("cvss31", _metrics("AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H")) is None
    assert outcome_label("usaf-rac", None) is None
    assert outcome_label(None, {"sev": "critical"}) is None
    assert outcome_label("does-not-exist", {"x": 1}) is None
    assert outcome_label("usaf-rac", {"sev": "critical"}) is None  # incomplete inputs


def test_outcome_label_falls_back_to_title_case():
    # OWASP has no outcome_labels; its tokens are severity names.
    assert outcome_label("owasp-rr", _owasp_inputs(8, 8)) == "Critical"


# ── policy resolution ────────────────────────────────────────────────

_ALL = ["cvss31", "dread", "owasp-rr", "usaf-rac"]
_NO_SITE = {"enabled_models": None, "default_model": None, "locked_model": None}


def test_policy_defaults_to_everything():
    p = resolve_effective(_NO_SITE, None, None, _ALL)
    assert p == {"allowed": _ALL, "default": "cvss31", "locked": False}


def test_policy_site_lock_wins_over_engagement():
    site = {**_NO_SITE, "locked_model": "usaf-rac"}
    p = resolve_effective(site, ["dread"], "dread", _ALL)
    assert p == {"allowed": ["usaf-rac"], "default": "usaf-rac", "locked": True}


def test_policy_engagement_narrows_site_enabled():
    site = {**_NO_SITE, "enabled_models": ["cvss31", "dread", "usaf-rac"], "default_model": "dread"}
    p = resolve_effective(site, ["usaf-rac", "owasp-rr"], None, _ALL)
    # owasp-rr isn't site-enabled, so it's dropped; one model left => locked.
    assert p == {"allowed": ["usaf-rac"], "default": "usaf-rac", "locked": True}


def test_policy_engagement_default_used_when_allowed():
    p = resolve_effective(_NO_SITE, ["cvss31", "dread"], "dread", _ALL)
    assert p["default"] == "dread" and p["locked"] is False


def test_policy_ignores_unknown_models():
    site = {**_NO_SITE, "enabled_models": ["gone"], "locked_model": "also-gone"}
    p = resolve_effective(site, None, None, _ALL)
    assert p["allowed"] == _ALL and p["locked"] is False


# ── report display ───────────────────────────────────────────────────


def _finding(**kw):
    base = dict(score_model=None, score_inputs=None, cvss_score=None, cvss_vector=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_report_score_info_legacy_finding_is_cvss31():
    from utils.report_generator import _score_info

    info = _score_info(_finding(cvss_score=9.8, cvss_vector="CVSS:3.1/AV:N"))
    assert info["label"] == "CVSS 3.1"
    assert info["text"] == "9.8  |  CVSS:3.1/AV:N"


def test_report_score_info_categorical_hides_nominal_score():
    from utils.report_generator import _score_info

    info = _score_info(_finding(score_model="usaf-rac", cvss_score=9.5,
                                score_inputs={"sev": "catastrophic", "prob": "frequent"},
                                cvss_vector="USAF-RAC/S:catastrophic/P:frequent"))
    assert info["label"] == "USAF Risk Assessment Matrix"
    assert info["numeric"] is False and info["score"] is None
    assert info["text"] == "Extremely High  |  USAF-RAC/S:catastrophic/P:frequent"


def test_report_score_label_mixed_models():
    from utils.report_generator import _score_label

    cvss = _finding(cvss_score=5.0)
    dread = _finding(score_model="dread", cvss_score=5.0)
    assert _score_label([cvss, cvss]) == "CVSS 3.1"
    assert _score_label([cvss, dread]) == "Score"
