"""CVSS 4.0 (CVSS-B base) scoring engine.

Faithful Python port of FIRST.org's cvss-v4-calculator (BSD-2-Clause):
macroVector() + cvss_score() from cvss_score.js, with the lookup / max_composed /
max_severity tables in cvss4_data.py.
"""
from __future__ import annotations

import math
from .cvss4_data import CVSS_LOOKUP, MAX_COMPOSED, MAX_SEVERITY

AV_LEVELS = {"N": 0.0, "A": 0.1, "L": 0.2, "P": 0.3}
PR_LEVELS = {"N": 0.0, "L": 0.1, "H": 0.2}
UI_LEVELS = {"N": 0.0, "P": 0.1, "A": 0.2}
AC_LEVELS = {"L": 0.0, "H": 0.1}
AT_LEVELS = {"N": 0.0, "P": 0.1}
VC_LEVELS = {"H": 0.0, "L": 0.1, "N": 0.2}
VI_LEVELS = {"H": 0.0, "L": 0.1, "N": 0.2}
VA_LEVELS = {"H": 0.0, "L": 0.1, "N": 0.2}
SC_LEVELS = {"H": 0.1, "L": 0.2, "N": 0.3}
SI_LEVELS = {"S": 0.0, "H": 0.1, "L": 0.2, "N": 0.3}
SA_LEVELS = {"S": 0.0, "H": 0.1, "L": 0.2, "N": 0.3}
CR_LEVELS = {"H": 0.0, "M": 0.1, "L": 0.2}
IR_LEVELS = {"H": 0.0, "M": 0.1, "L": 0.2}
AR_LEVELS = {"H": 0.0, "M": 0.1, "L": 0.2}

BASE_METRICS = ["AV", "AC", "AT", "PR", "UI", "VC", "VI", "VA", "SC", "SI", "SA"]
# Every metric referenced during scoring, defaulted to "X" (matches the official
# calculator, which always carries the full metric set).
_ALL_X = {m: "X" for m in (
    BASE_METRICS + ["E", "CR", "IR", "AR",
                    "MAV", "MAC", "MAT", "MPR", "MUI", "MVC", "MVI", "MVA",
                    "MSC", "MSI", "MSA"])}


def m(sel, metric):
    selected = sel.get(metric, "X")
    if metric == "E" and selected == "X":
        return "A"
    if metric in ("CR", "IR", "AR") and selected == "X":
        return "H"
    mkey = "M" + metric
    if mkey in sel:
        modified = sel[mkey]
        if modified != "X":
            return modified
    return selected


def macro_vector(sel):
    # EQ1
    if m(sel, "AV") == "N" and m(sel, "PR") == "N" and m(sel, "UI") == "N":
        eq1 = 0
    elif ((m(sel, "AV") == "N" or m(sel, "PR") == "N" or m(sel, "UI") == "N")
          and not (m(sel, "AV") == "N" and m(sel, "PR") == "N" and m(sel, "UI") == "N")
          and not (m(sel, "AV") == "P")):
        eq1 = 1
    else:
        eq1 = 2
    # EQ2
    eq2 = 0 if (m(sel, "AC") == "L" and m(sel, "AT") == "N") else 1
    # EQ3
    if m(sel, "VC") == "H" and m(sel, "VI") == "H":
        eq3 = 0
    elif (m(sel, "VC") == "H" or m(sel, "VI") == "H" or m(sel, "VA") == "H"):
        eq3 = 1
    else:
        eq3 = 2
    # EQ4
    if m(sel, "MSI") == "S" or m(sel, "MSA") == "S":
        eq4 = 0
    elif (m(sel, "SC") == "H" or m(sel, "SI") == "H" or m(sel, "SA") == "H"):
        eq4 = 1
    else:
        eq4 = 2
    # EQ5
    if m(sel, "E") == "A":
        eq5 = 0
    elif m(sel, "E") == "P":
        eq5 = 1
    else:
        eq5 = 2
    # EQ6
    if ((m(sel, "CR") == "H" and m(sel, "VC") == "H")
            or (m(sel, "IR") == "H" and m(sel, "VI") == "H")
            or (m(sel, "AR") == "H" and m(sel, "VA") == "H")):
        eq6 = 0
    else:
        eq6 = 1
    return f"{eq1}{eq2}{eq3}{eq4}{eq5}{eq6}"


def _extract_value_metric(metric, s):
    extracted = s[s.index(metric) + len(metric) + 1:]
    slash = extracted.find("/")
    return extracted[:slash] if slash > 0 else extracted


def _get_eq_maxes(mv, eq):
    return MAX_COMPOSED["eq" + str(eq)][int(mv[eq - 1])]


def _lk(key):
    return CVSS_LOOKUP.get(key, math.nan)


def cvss_score(sel, mv):
    # Shortcut: no impact on any system.
    if all(m(sel, k) == "N" for k in ("VC", "VI", "VA", "SC", "SI", "SA")):
        return 0.0

    value = CVSS_LOOKUP[mv]
    eq1, eq2, eq3, eq4, eq5, eq6 = (int(c) for c in mv)

    eq1_next = f"{eq1 + 1}{eq2}{eq3}{eq4}{eq5}{eq6}"
    eq2_next = f"{eq1}{eq2 + 1}{eq3}{eq4}{eq5}{eq6}"

    eq3eq6_left = eq3eq6_right = None
    if eq3 == 1 and eq6 == 1:
        eq3eq6_next = f"{eq1}{eq2}{eq3 + 1}{eq4}{eq5}{eq6}"
    elif eq3 == 0 and eq6 == 1:
        eq3eq6_next = f"{eq1}{eq2}{eq3 + 1}{eq4}{eq5}{eq6}"
    elif eq3 == 1 and eq6 == 0:
        eq3eq6_next = f"{eq1}{eq2}{eq3}{eq4}{eq5}{eq6 + 1}"
    elif eq3 == 0 and eq6 == 0:
        eq3eq6_left = f"{eq1}{eq2}{eq3}{eq4}{eq5}{eq6 + 1}"
        eq3eq6_right = f"{eq1}{eq2}{eq3 + 1}{eq4}{eq5}{eq6}"
        eq3eq6_next = None
    else:
        eq3eq6_next = f"{eq1}{eq2}{eq3 + 1}{eq4}{eq5}{eq6 + 1}"

    eq4_next = f"{eq1}{eq2}{eq3}{eq4 + 1}{eq5}{eq6}"
    eq5_next = f"{eq1}{eq2}{eq3}{eq4}{eq5 + 1}{eq6}"

    score_eq1_next = _lk(eq1_next)
    score_eq2_next = _lk(eq2_next)
    if eq3 == 0 and eq6 == 0:
        left = _lk(eq3eq6_left)
        right = _lk(eq3eq6_right)
        score_eq3eq6_next = left if left > right else right
    else:
        score_eq3eq6_next = _lk(eq3eq6_next)
    score_eq4_next = _lk(eq4_next)
    score_eq5_next = _lk(eq5_next)

    eq1_maxes = _get_eq_maxes(mv, 1)
    eq2_maxes = _get_eq_maxes(mv, 2)
    eq3_eq6_maxes = _get_eq_maxes(mv, 3)[mv[5]]
    eq4_maxes = _get_eq_maxes(mv, 4)
    eq5_maxes = _get_eq_maxes(mv, 5)

    max_vectors = []
    for a in eq1_maxes:
        for b in eq2_maxes:
            for c in eq3_eq6_maxes:
                for d in eq4_maxes:
                    for e in eq5_maxes:
                        max_vectors.append(a + b + c + d + e)

    # distances default (persist after the break, matching the JS)
    sd = {}
    for max_vector in max_vectors:
        sd = {
            "AV": AV_LEVELS[m(sel, "AV")] - AV_LEVELS[_extract_value_metric("AV", max_vector)],
            "PR": PR_LEVELS[m(sel, "PR")] - PR_LEVELS[_extract_value_metric("PR", max_vector)],
            "UI": UI_LEVELS[m(sel, "UI")] - UI_LEVELS[_extract_value_metric("UI", max_vector)],
            "AC": AC_LEVELS[m(sel, "AC")] - AC_LEVELS[_extract_value_metric("AC", max_vector)],
            "AT": AT_LEVELS[m(sel, "AT")] - AT_LEVELS[_extract_value_metric("AT", max_vector)],
            "VC": VC_LEVELS[m(sel, "VC")] - VC_LEVELS[_extract_value_metric("VC", max_vector)],
            "VI": VI_LEVELS[m(sel, "VI")] - VI_LEVELS[_extract_value_metric("VI", max_vector)],
            "VA": VA_LEVELS[m(sel, "VA")] - VA_LEVELS[_extract_value_metric("VA", max_vector)],
            "SC": SC_LEVELS[m(sel, "SC")] - SC_LEVELS[_extract_value_metric("SC", max_vector)],
            "SI": SI_LEVELS[m(sel, "SI")] - SI_LEVELS[_extract_value_metric("SI", max_vector)],
            "SA": SA_LEVELS[m(sel, "SA")] - SA_LEVELS[_extract_value_metric("SA", max_vector)],
            "CR": CR_LEVELS[m(sel, "CR")] - CR_LEVELS[_extract_value_metric("CR", max_vector)],
            "IR": IR_LEVELS[m(sel, "IR")] - IR_LEVELS[_extract_value_metric("IR", max_vector)],
            "AR": AR_LEVELS[m(sel, "AR")] - AR_LEVELS[_extract_value_metric("AR", max_vector)],
        }
        if any(v < 0 for v in sd.values()):
            continue
        break

    cur_eq1 = sd["AV"] + sd["PR"] + sd["UI"]
    cur_eq2 = sd["AC"] + sd["AT"]
    cur_eq3eq6 = sd["VC"] + sd["VI"] + sd["VA"] + sd["CR"] + sd["IR"] + sd["AR"]
    cur_eq4 = sd["SC"] + sd["SI"] + sd["SA"]
    cur_eq5 = 0.0

    step = 0.1
    avail_eq1 = value - score_eq1_next
    avail_eq2 = value - score_eq2_next
    avail_eq3eq6 = value - score_eq3eq6_next
    avail_eq4 = value - score_eq4_next
    avail_eq5 = value - score_eq5_next

    n_existing = 0
    norm_eq1 = norm_eq2 = norm_eq3eq6 = norm_eq4 = norm_eq5 = 0.0

    max_sev_eq1 = MAX_SEVERITY["eq1"][eq1] * step
    max_sev_eq2 = MAX_SEVERITY["eq2"][eq2] * step
    max_sev_eq3eq6 = MAX_SEVERITY["eq3eq6"][eq3][eq6] * step
    max_sev_eq4 = MAX_SEVERITY["eq4"][eq4] * step

    if not math.isnan(avail_eq1):
        n_existing += 1
        norm_eq1 = avail_eq1 * (cur_eq1 / max_sev_eq1)
    if not math.isnan(avail_eq2):
        n_existing += 1
        norm_eq2 = avail_eq2 * (cur_eq2 / max_sev_eq2)
    if not math.isnan(avail_eq3eq6):
        n_existing += 1
        norm_eq3eq6 = avail_eq3eq6 * (cur_eq3eq6 / max_sev_eq3eq6)
    if not math.isnan(avail_eq4):
        n_existing += 1
        norm_eq4 = avail_eq4 * (cur_eq4 / max_sev_eq4)
    if not math.isnan(avail_eq5):
        n_existing += 1
        norm_eq5 = avail_eq5 * 0.0

    if n_existing == 0:
        mean_distance = 0.0
    else:
        mean_distance = (norm_eq1 + norm_eq2 + norm_eq3eq6 + norm_eq4 + norm_eq5) / n_existing

    value -= mean_distance
    value = max(0.0, min(10.0, value))
    # JS Math.round is half-up (floor(x+0.5)); Python round() is half-to-even,
    # which diverges at exact .5 boundaries. Match the reference exactly.
    return math.floor(value * 10 + 0.5) / 10


def calculate(metrics: dict):
    """metrics: the 11 base metric letters. Returns (score, vector_string)."""
    sel = dict(_ALL_X)
    for k in BASE_METRICS:
        if metrics.get(k):
            sel[k] = metrics[k]
    mv = macro_vector(sel)
    score = cvss_score(sel, mv)
    vector = "CVSS:4.0/" + "/".join(f"{k}:{sel[k]}" for k in BASE_METRICS)
    return score, vector
