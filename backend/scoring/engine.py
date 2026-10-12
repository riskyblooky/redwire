"""The scoring engine: interpret a ``ScoringModel`` formula over metric inputs.

Formulas are built from a fixed, safe set of primitives (no arbitrary code /
expression evaluation). A formula node is one of:

    {"op": "average",      "of": [ref, ...], "scale": {...}?}
    {"op": "weighted_sum", "of": [{"metric": id, "weight": w} | ref, ...],
                            "normalize": bool?, "scale": {...}?}
    {"op": "product",      "of": [ref, ...], "scale": {...}?}
    {"op": "max" | "min",  "of": [ref, ...]}
    {"op": "bucket",       "of": ref, "bands": [{"max": n, "label": s}, ...]}
    {"op": "matrix",       "axes": [refA, refB], "cells": {"tokA|tokB": outcome}}
    {"op": "lookup_table", "keys": [ref, ...], "table": {"t1|t2|...": outcome}}
    {"op": "pipeline",     "steps": [{"id": s, ...node}, ...], "output": s}
    {"engine": "builtin-cvss31"}                      # delegate to a named engine

A ``ref`` is a metric id, a literal number, or ``"$stepId"`` (a pipeline step
result). ``numeric`` refs resolve a select to its option ``weight``; ``token``
refs (matrix/lookup axes) resolve a select to its chosen ``value``.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Union

from scoring.cvss31 import calculate_from_metrics as _cvss31_calc
from scoring.severity import coerce_severity, score_to_severity
from scoring.types import ScoreResult, ScoringModel

Number = Union[int, float]


class ScoringError(ValueError):
    """Raised when a model or its inputs cannot be evaluated."""


# ─── Reference resolution ─────────────────────────────────────────────────────

def _resolve_number(ref: Any, model: ScoringModel, inputs: Dict[str, Any], steps: Dict[str, Any]) -> float:
    if isinstance(ref, (int, float)):
        return float(ref)
    if isinstance(ref, str) and ref.startswith("$"):
        val = steps.get(ref[1:])
        try:
            return float(val)
        except (TypeError, ValueError):
            raise ScoringError(f"step '{ref}' did not produce a number")
    metric = model.metric(ref) if isinstance(ref, str) else None
    if metric is not None:
        raw = inputs.get(metric.id)
        if raw is None or raw == "":
            raise ScoringError(f"missing value for metric '{metric.id}'")
        if metric.type == "number":
            try:
                return float(raw)
            except (TypeError, ValueError):
                raise ScoringError(f"metric '{metric.id}' is not a number: {raw!r}")
        # select -> option weight
        for opt in metric.options or []:
            if opt.value == raw:
                if opt.weight is None:
                    raise ScoringError(f"option '{raw}' of metric '{metric.id}' has no numeric weight")
                return float(opt.weight)
        raise ScoringError(f"unknown option '{raw}' for metric '{metric.id}'")
    # literal numeric string
    try:
        return float(ref)
    except (TypeError, ValueError):
        raise ScoringError(f"cannot resolve numeric reference {ref!r}")


def _resolve_token(ref: Any, model: ScoringModel, inputs: Dict[str, Any], steps: Dict[str, Any]) -> str:
    if isinstance(ref, str) and ref.startswith("$"):
        val = steps.get(ref[1:])
        if val is None:
            raise ScoringError(f"step '{ref}' has no value")
        return str(val)
    metric = model.metric(ref) if isinstance(ref, str) else None
    if metric is not None:
        raw = inputs.get(metric.id)
        if raw is None or raw == "":
            raise ScoringError(f"missing value for metric '{metric.id}'")
        return str(raw)
    return str(ref)


def _apply_scale(value: float, scale: Optional[Dict[str, Any]]) -> float:
    """Optional linear remap {"from": [a, b], "to": [c, d]} with clamping."""
    if not scale:
        return value
    a, b = scale["from"]
    c, d = scale["to"]
    if b == a:
        return c
    mapped = c + (value - a) * (d - c) / (b - a)
    lo, hi = (c, d) if c <= d else (d, c)
    return max(lo, min(hi, mapped))


# ─── Primitive dispatch ───────────────────────────────────────────────────────

def _eval(node: Dict[str, Any], model: ScoringModel, inputs: Dict[str, Any], steps: Dict[str, Any]) -> Union[float, str]:
    if not isinstance(node, dict):
        raise ScoringError(f"formula node must be an object, got {type(node).__name__}")

    op = node.get("op")

    if op == "pipeline":
        for step in node.get("steps", []):
            sid = step.get("id")
            if not sid:
                raise ScoringError("pipeline step missing 'id'")
            steps[sid] = _eval(step, model, inputs, steps)
        out = node.get("output")
        if out is not None:
            if out not in steps:
                raise ScoringError(f"pipeline output '{out}' not computed")
            return steps[out]
        return list(steps.values())[-1] if steps else 0.0

    if op == "average":
        vals = [_resolve_number(r, model, inputs, steps) for r in node["of"]]
        res = sum(vals) / len(vals) if vals else 0.0
        return _apply_scale(res, node.get("scale"))

    if op == "weighted_sum":
        total = 0.0
        wsum = 0.0
        for item in node["of"]:
            if isinstance(item, dict):
                v = _resolve_number(item["metric"], model, inputs, steps)
                wt = float(item.get("weight", 1.0))
            else:
                v = _resolve_number(item, model, inputs, steps)
                wt = 1.0
            total += v * wt
            wsum += wt
        res = total / wsum if (node.get("normalize") and wsum) else total
        return _apply_scale(res, node.get("scale"))

    if op == "product":
        res = 1.0
        for r in node["of"]:
            res *= _resolve_number(r, model, inputs, steps)
        return _apply_scale(res, node.get("scale"))

    if op in ("max", "min"):
        vals = [_resolve_number(r, model, inputs, steps) for r in node["of"]]
        if not vals:
            raise ScoringError(f"'{op}' needs at least one operand")
        return max(vals) if op == "max" else min(vals)

    if op == "bucket":
        num = _resolve_number(node["of"], model, inputs, steps)
        bands = sorted(node["bands"], key=lambda b: float(b["max"]))
        for band in bands:
            if num <= float(band["max"]):
                return str(band["label"])
        return str(bands[-1]["label"])

    if op == "matrix":
        axis_a, axis_b = node["axes"]
        ta = _resolve_token(axis_a, model, inputs, steps)
        tb = _resolve_token(axis_b, model, inputs, steps)
        key = f"{ta}|{tb}"
        cells = node["cells"]
        if key not in cells:
            raise ScoringError(f"matrix has no cell for '{key}'")
        return str(cells[key])

    if op == "lookup_table":
        toks = [_resolve_token(r, model, inputs, steps) for r in node["keys"]]
        key = "|".join(toks)
        table = node["table"]
        if key not in table:
            raise ScoringError(f"lookup_table has no entry for '{key}'")
        return str(table[key])

    raise ScoringError(f"unknown formula op {op!r}")


# ─── Vector rendering ─────────────────────────────────────────────────────────

_PLACEHOLDER = re.compile(r"\{([a-zA-Z0-9_]+)\}")


def _render_vector(template: str, inputs: Dict[str, Any]) -> str:
    return _PLACEHOLDER.sub(lambda m: str(inputs.get(m.group(1), "")), template)


# ─── Public entry point ───────────────────────────────────────────────────────

def evaluate(model: ScoringModel, inputs: Dict[str, Any]) -> ScoreResult:
    """Evaluate ``model`` over ``inputs`` and return a normalized ScoreResult.

    Raises :class:`ScoringError` for an un-evaluable model or incomplete inputs.
    """
    inputs = dict(inputs or {})
    formula = model.formula or {}
    vector: Optional[str] = None
    numeric_value: Optional[float] = None
    token_value: Optional[str] = None

    if "engine" in formula:
        eng = formula["engine"]
        if eng == "builtin-cvss31":
            numeric_value, vector = _cvss31_calc(inputs)
        else:
            raise ScoringError(f"unknown engine {eng!r} (no provider registered)")
    else:
        result = _eval(formula, model, inputs, {})
        if isinstance(result, (int, float)):
            numeric_value = float(result)
        else:
            token_value = str(result)

    mapping = model.severity
    if mapping.from_ == "bands":
        if numeric_value is None:
            raise ScoringError(f"model '{model.id}' band-maps severity but produced no number")
        severity = score_to_severity(numeric_value, mapping.bands)
        score = numeric_value
        outcome = None
    else:  # map
        outcome = token_value if token_value is not None else (
            None if numeric_value is None else str(numeric_value)
        )
        if outcome is None or not mapping.map or outcome not in mapping.map:
            raise ScoringError(f"model '{model.id}' has no severity mapping for outcome {outcome!r}")
        severity = coerce_severity(mapping.map[outcome])
        score = None
        if model.nominal_score:
            score = model.nominal_score.get(severity)

    if vector is None and model.vector_template:
        vector = _render_vector(model.vector_template, inputs)

    return ScoreResult(
        model_id=model.id,
        score=score,
        outcome=outcome,
        severity=severity,
        vector=vector,
        inputs=inputs,
    )
