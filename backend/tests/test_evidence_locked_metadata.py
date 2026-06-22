"""Chain-of-custody guard extends to metadata fields that drive report rendering.

GHSA-287x-h6p3-frfv shipped a byte-level chain-of-custody guard that
locks evidence once its parent finding hits VERIFIED — delete /
replace-file / strip-exif all 409 with "Evidence is locked". The
follow-up bundled here extends the same guard to the metadata flags
that change report rendering for the verified finding:

  - ``include_in_report``: silently omitting verified proof from the
    next report regen.
  - ``classification_level`` / ``classification_suffix``: silently
    re-banner-ing the verified proof.

``description`` is intentionally *not* covered: it's an annotation
(commentary, not load-bearing on the verification) and locking it
would block legitimate post-VERIFY context-adding.

The guard is exercised through a small, importable constant
(``EVIDENCE_COC_LOCKED_FIELDS``); these tests pin the constant's
contents and the description-is-not-locked invariant. The full HTTP
round-trip lives in the v1.2.0 GHSA-287x PoC and isn't reproduced
here.
"""

from __future__ import annotations

from routers.evidence import EVIDENCE_COC_LOCKED_FIELDS


def test_locked_set_contains_the_three_render_drivers():
    assert EVIDENCE_COC_LOCKED_FIELDS == frozenset({
        "include_in_report",
        "classification_level",
        "classification_suffix",
    })


def test_description_is_not_locked():
    # ``description`` is the annotation field — locking it would block
    # legitimate post-VERIFY commentary and creates no chain-of-custody
    # signal because it doesn't affect report rendering.
    assert "description" not in EVIDENCE_COC_LOCKED_FIELDS


def test_set_intersection_idiom_works_with_dict_keys():
    # The call site uses ``EVIDENCE_COC_LOCKED_FIELDS.intersection(update_data)``
    # where ``update_data`` is a dict. The intersection should consume
    # dict-keys iteration directly. Pin that contract so a future
    # rewrite that switches the call shape doesn't silently turn the
    # guard into a no-op (e.g. ``set & some_value`` against a non-set
    # raises TypeError, which would be caught — but
    # ``set.intersection(some_iterable)`` against a list of values
    # would *succeed* with the wrong result).
    locked_payload = {"include_in_report": False, "description": "x"}
    assert EVIDENCE_COC_LOCKED_FIELDS.intersection(locked_payload) == {"include_in_report"}

    unlocked_payload = {"description": "just commentary"}
    assert EVIDENCE_COC_LOCKED_FIELDS.intersection(unlocked_payload) == set()

    empty_payload: dict = {}
    assert EVIDENCE_COC_LOCKED_FIELDS.intersection(empty_payload) == set()


def test_locked_set_is_immutable():
    """frozenset prevents accidental mutation (e.g. some other module
    appending to the set at import time and reducing the lock surface
    silently)."""
    assert isinstance(EVIDENCE_COC_LOCKED_FIELDS, frozenset)
