"""Classification / portion-marking engine (`utils/marking.py`).

Pure-unit coverage of the resolution / roll-up / mark-formatting contract
the PDF generator relies on:

  - ranking + highest-marking roll-up (`highest`, `lowest_level`)
  - inheritance + ceiling clamp (`resolve`)
  - scheme idioms: TLP 2.0 vs IC/DoD-custom (`portion_mark`, `banner`,
    `banner_top_and_bottom`, `is_tlp`)
  - placement-policy passthroughs
  - the pre-generation lint (`lint_marking`) — blocking vs warning vs clean,
    plus evidence-inherits-its-finding.

Profiles/engagements are duck-typed (the engine only does getattr), so
SimpleNamespace stands in for the real ORM rows.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from utils.marking import MarkingEngine, lint_marking


# ── fixtures / builders ──────────────────────────────────────────────

# IC/DoD-style ladder (rank ascends with sensitivity).
IC_LEVELS = [
    {"abbreviation": "U", "rank": 0, "full_name": "UNCLASSIFIED",
     "banner_color": "#008000", "text_color": "#FFFFFF"},
    {"abbreviation": "C", "rank": 1, "full_name": "CONFIDENTIAL",
     "banner_color": "#0000FF", "text_color": "#FFFFFF"},
    {"abbreviation": "S", "rank": 2, "full_name": "SECRET",
     "banner_color": "#FF0000", "text_color": "#FFFFFF"},
    {"abbreviation": "TS", "rank": 3, "full_name": "TOP SECRET",
     "banner_color": "#FFA500", "text_color": "#000000"},
]

TLP_LEVELS = [
    {"abbreviation": "CLEAR", "rank": 0, "banner_color": "#FFFFFF", "text_color": "#000000"},
    {"abbreviation": "GREEN", "rank": 1, "banner_color": "#33FF00", "text_color": "#000000"},
    {"abbreviation": "AMBER", "rank": 2, "banner_color": "#FFC000", "text_color": "#000000"},
    {"abbreviation": "RED", "rank": 3, "banner_color": "#FF0033", "text_color": "#FFFFFF"},
]


def make_profile(scheme="IC_DOD", levels=None, **extra):
    return SimpleNamespace(scheme=scheme, levels=levels if levels is not None else IC_LEVELS, **extra)


def make_engagement(default=None, suffix=None, ceiling=None):
    return SimpleNamespace(
        default_classification_level=default,
        default_classification_suffix=suffix,
        ceiling_classification_level=ceiling,
    )


def make_engine(profile=None, engagement=None):
    return MarkingEngine(profile or make_profile(), engagement or make_engagement())


# ── scheme extraction ────────────────────────────────────────────────


class TestSchemeExtraction:
    def test_plain_string_scheme(self):
        assert make_engine(make_profile(scheme="TLP_2_0")).scheme == "TLP_2_0"

    def test_enum_like_scheme_uses_value(self):
        scheme = SimpleNamespace(value="TLP_2_0")
        assert make_engine(make_profile(scheme=scheme)).scheme == "TLP_2_0"

    def test_missing_levels_yields_empty_maps(self):
        # `levels` attribute present but None → engine's `... or []` guard.
        eng = make_engine(SimpleNamespace(scheme="IC_DOD", levels=None))
        assert eng.levels_by_abbr == {}
        assert eng._ordered == []

    def test_levels_without_abbreviation_skipped(self):
        levels = [{"rank": 0}, {"abbreviation": "S", "rank": 2}]
        eng = make_engine(make_profile(levels=levels))
        assert list(eng.levels_by_abbr) == ["S"]


# ── ranking / roll-up ────────────────────────────────────────────────


class TestRankingRollup:
    def test_highest_picks_top_rank(self):
        assert make_engine().highest(["U", "S", "C"]) == "S"

    def test_highest_ignores_none_and_blank(self):
        assert make_engine().highest([None, "U", "", "S", None]) == "S"

    def test_highest_of_empty_is_none(self):
        assert make_engine().highest([]) is None

    def test_highest_of_only_unknown_is_none(self):
        # Unknown abbrs rank -1, which never beats the -1 starting best_rank.
        assert make_engine().highest(["ZZ", "QQ"]) is None

    def test_highest_known_beats_unknown(self):
        assert make_engine().highest(["ZZ", "U"]) == "U"

    def test_rank_lookup(self):
        eng = make_engine()
        assert eng._rank("TS") == 3
        assert eng._rank("U") == 0
        assert eng._rank("nope") == -1
        assert eng._rank(None) == -1

    def test_lowest_level(self):
        assert make_engine().lowest_level() == "U"

    def test_lowest_level_empty_ladder(self):
        assert make_engine(make_profile(levels=[])).lowest_level() is None

    def test_lowest_level_respects_rank_not_order(self):
        # Rank, not list position, decides "lowest".
        levels = [
            {"abbreviation": "S", "rank": 2},
            {"abbreviation": "U", "rank": 0},
            {"abbreviation": "C", "rank": 1},
        ]
        assert make_engine(make_profile(levels=levels)).lowest_level() == "U"


# ── resolution: inheritance + ceiling clamp ──────────────────────────


class TestResolve:
    def test_explicit_level_kept_with_suffix(self):
        eng = make_engine(engagement=make_engagement(default="U"))
        assert eng.resolve("S", "//SAR/1") == ("S", "//SAR/1")

    def test_no_level_inherits_engagement_default(self):
        eng = make_engine(engagement=make_engagement(default="C", suffix="//X"))
        assert eng.resolve(None, None) == ("C", "//X")

    def test_no_level_no_default_is_none(self):
        eng = make_engine(engagement=make_engagement())
        assert eng.resolve(None, None) == (None, None)

    def test_over_ceiling_clamped_and_suffix_dropped(self):
        eng = make_engine(engagement=make_engagement(ceiling="C"))
        # TS (rank 3) exceeds ceiling C (rank 1) → clamp to C, drop caveat.
        assert eng.resolve("TS", "//SAR/1") == ("C", None)

    def test_at_ceiling_not_clamped(self):
        eng = make_engine(engagement=make_engagement(ceiling="S"))
        assert eng.resolve("S", "//X") == ("S", "//X")

    def test_below_ceiling_not_clamped(self):
        eng = make_engine(engagement=make_engagement(ceiling="S"))
        assert eng.resolve("U", None) == ("U", None)

    def test_inherited_default_also_clamped(self):
        # Default S exceeds ceiling C → inheritance then clamp.
        eng = make_engine(engagement=make_engagement(default="S", suffix="//Y", ceiling="C"))
        assert eng.resolve(None, None) == ("C", None)


# ── scheme flags & passthroughs ──────────────────────────────────────


class TestSchemeFlags:
    def test_is_tlp_true(self):
        assert make_engine(make_profile(scheme="TLP_2_0")).is_tlp is True

    def test_is_tlp_false_for_ic(self):
        assert make_engine(make_profile(scheme="IC_DOD")).is_tlp is False

    def test_banner_top_and_bottom_is_negation_of_tlp(self):
        assert make_engine(make_profile(scheme="IC_DOD")).banner_top_and_bottom is True
        assert make_engine(make_profile(scheme="TLP_2_0")).banner_top_and_bottom is False

    def test_inline_marks_default_true_when_unset(self):
        # Attribute absent → getattr default None → engine treats as True.
        assert make_engine(make_profile()).inline_marks is True

    def test_inline_marks_explicit_false(self):
        assert make_engine(make_profile(inline_portion_marks=False)).inline_marks is False

    def test_inline_marks_explicit_true(self):
        assert make_engine(make_profile(inline_portion_marks=True)).inline_marks is True

    def test_static_heading_mode_default_lowest(self):
        assert make_engine(make_profile()).static_heading_mode == "LOWEST"

    def test_static_heading_mode_override(self):
        assert make_engine(make_profile(static_heading_marks="INHERIT")).static_heading_mode == "INHERIT"


class TestPassthroughs:
    def test_anchor_lists_copy_and_default_empty(self):
        eng = make_engine(make_profile())
        assert eng.image_anchors == []
        assert eng.table_anchors == []

    def test_anchor_lists_passthrough(self):
        eng = make_engine(make_profile(
            image_mark_anchors=["TOP_LEFT"], table_mark_anchors=["CAPTION"]))
        assert eng.image_anchors == ["TOP_LEFT"]
        assert eng.table_anchors == ["CAPTION"]

    def test_anchor_list_is_a_copy(self):
        src = ["TOP_LEFT"]
        eng = make_engine(make_profile(image_mark_anchors=src))
        eng.image_anchors.append("X")
        assert src == ["TOP_LEFT"]  # original untouched

    def test_bool_passthroughs_default(self):
        eng = make_engine(make_profile())
        assert eng.per_row is False
        assert eng.stamp_images is False
        assert eng.show_legend is True  # default True when attr absent

    def test_bool_passthroughs_set(self):
        eng = make_engine(make_profile(
            table_per_row_marks=True, stamp_images=True, show_legend=False))
        assert eng.per_row is True
        assert eng.stamp_images is True
        assert eng.show_legend is False

    def test_distribution_statement(self):
        assert make_engine(make_profile()).distribution_statement is None
        assert make_engine(make_profile(distribution_statement="D. Distro")).distribution_statement == "D. Distro"


# ── portion marks ────────────────────────────────────────────────────


class TestPortionMark:
    def test_ic_parenthetical(self):
        assert make_engine(make_profile(scheme="IC_DOD")).portion_mark("S", None) == "(S)"

    def test_ic_with_suffix(self):
        assert make_engine(make_profile(scheme="IC_DOD")).portion_mark("S", "//SAR/123") == "(S//SAR/123)"

    def test_tlp_token(self):
        eng = make_engine(make_profile(scheme="TLP_2_0", levels=TLP_LEVELS))
        assert eng.portion_mark("AMBER", None) == "TLP:AMBER"

    def test_tlp_token_with_suffix(self):
        eng = make_engine(make_profile(scheme="TLP_2_0", levels=TLP_LEVELS))
        assert eng.portion_mark("AMBER", "+STRICT") == "TLP:AMBER+STRICT"

    def test_no_level_is_empty(self):
        assert make_engine().portion_mark(None, "//x") == ""

    def test_inline_marks_off_is_empty(self):
        eng = make_engine(make_profile(inline_portion_marks=False))
        assert eng.portion_mark("S", None) == ""


# ── banner ───────────────────────────────────────────────────────────


class TestBanner:
    def test_none_level(self):
        assert make_engine().banner(None) is None

    def test_unknown_level(self):
        assert make_engine().banner("ZZ") is None

    def test_ic_uses_full_name_and_colors(self):
        eng = make_engine(make_profile(scheme="IC_DOD"))
        assert eng.banner("S") == ("SECRET", "#FF0000", "#FFFFFF")

    def test_tlp_falls_back_to_prefixed_token_when_no_full_name(self):
        eng = make_engine(make_profile(scheme="TLP_2_0", levels=TLP_LEVELS))
        text, bg, fg = eng.banner("AMBER")
        assert text == "TLP:AMBER"
        assert (bg, fg) == ("#FFC000", "#000000")

    def test_color_defaults_when_missing(self):
        levels = [{"abbreviation": "X", "rank": 0}]  # no colors, no full_name
        eng = make_engine(make_profile(scheme="IC_DOD", levels=levels))
        text, bg, fg = eng.banner("X")
        # No full_name + not TLP → text is the bare abbreviation.
        assert text == "X"
        assert (bg, fg) == ("#1E293B", "#FFFFFF")


class TestLegendEntries:
    def test_entries_in_order(self):
        entries = make_engine(make_profile(scheme="IC_DOD")).legend_entries()
        assert [e[0] for e in entries] == ["U", "C", "S", "TS"]
        assert entries[2] == ("S", "SECRET", "#FF0000", "#FFFFFF")

    def test_entry_color_defaults(self):
        levels = [{"abbreviation": "X"}]
        entries = make_engine(make_profile(levels=levels)).legend_entries()
        assert entries == [("X", "", "#1E293B", "#FFFFFF")]


# ── lint_marking ─────────────────────────────────────────────────────


def portion(level=None, suffix=None, title="?", **extra):
    return SimpleNamespace(
        classification_level=level, classification_suffix=suffix, title=title, **extra)


class TestLintMarking:
    def test_banner_only_profile_short_circuits(self):
        eng = make_engine(make_profile(scheme="TLP_2_0", levels=TLP_LEVELS,
                                       inline_portion_marks=False))
        blocking, warnings = lint_marking(
            eng, [portion(title="s")], [portion(title="f")], [], [])
        assert blocking == [] and warnings == []

    def test_blocking_when_no_mark_and_no_default(self):
        eng = make_engine(engagement=make_engagement())  # no default
        blocking, warnings = lint_marking(
            eng, [portion(title="Intro")], [], [], [])
        assert blocking == ["Section: Intro"]
        assert warnings == []

    def test_warning_when_inherited_from_default(self):
        eng = make_engine(engagement=make_engagement(default="U"))
        blocking, warnings = lint_marking(
            eng, [portion(title="Intro")], [], [], [])
        assert blocking == []
        assert warnings == ["Section: Intro"]

    def test_explicit_mark_is_clean(self):
        eng = make_engine(engagement=make_engagement(default="U"))
        blocking, warnings = lint_marking(
            eng, [portion(level="S", title="Intro")], [], [], [])
        assert blocking == [] and warnings == []

    def test_all_entity_kinds_labelled(self):
        eng = make_engine(engagement=make_engagement())  # everything blocks
        blocking, _ = lint_marking(
            eng,
            [portion(title="Sec")],
            [portion(title="Find")],
            [portion(title="TC")],
            [portion(title="Clean")],
        )
        assert blocking == [
            "Section: Sec", "Finding: Find", "Test case: TC", "Cleanup artifact: Clean",
        ]

    def test_evidence_inherits_finding_effective_mark(self):
        # Finding explicitly S; its included evidence has no mark and inherits
        # S from the parent → not blocking, but flagged as a warning (it's
        # riding an inherited mark rather than carrying its own).
        eng = make_engine(engagement=make_engagement())
        ev = SimpleNamespace(
            classification_level=None, classification_suffix=None,
            include_in_report=True, original_filename="shot.png")
        finding = portion(level="S", title="F", evidence=[ev])
        blocking, warnings = lint_marking(eng, [], [finding], [], [])
        assert blocking == []
        assert warnings == ["Evidence: shot.png"]

    def test_excluded_evidence_not_assessed(self):
        eng = make_engine(engagement=make_engagement())
        ev = SimpleNamespace(
            classification_level=None, classification_suffix=None,
            include_in_report=False, original_filename="shot.png")
        finding = portion(level="S", title="F", evidence=[ev])
        blocking, warnings = lint_marking(eng, [], [finding], [], [])
        # Only the finding is assessed; excluded evidence is skipped entirely.
        assert blocking == [] and warnings == []

    def test_included_evidence_blocks_when_finding_unmarked(self):
        # Finding has no mark and no default → finding blocks AND its
        # evidence (parent_eff None) blocks too.
        eng = make_engine(engagement=make_engagement())
        ev = SimpleNamespace(
            classification_level=None, classification_suffix=None,
            include_in_report=True, original_filename="shot.png")
        finding = portion(title="F", evidence=[ev])
        blocking, _ = lint_marking(eng, [], [finding], [], [])
        assert blocking == ["Finding: F", "Evidence: shot.png"]
