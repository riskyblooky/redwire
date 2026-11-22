"""PDF inline markdown: emphasis only where CommonMark would put it, and
backslash escapes (how the editor saves a literal _ or *) are honoured."""

from __future__ import annotations

import pytest

from utils.report_generator import _md_inline_to_rl as rl


@pytest.mark.parametrize("text", [
    "xp_cmdshell via sp_configure",
    "a_b_c and d_e",
    "2 * 3 * 4",
    "~/.ssh/id_rsa and ~/.bashrc",
    "a ^ b ^ c",
])
def test_identifiers_paths_and_arithmetic_stay_plain(text):
    assert rl(text) == text


def test_backslash_escapes_are_literal():
    assert rl(r"xp\_cmdshell via sp\_configure") == "xp_cmdshell via sp_configure"
    assert rl(r"literal \*star\*") == "literal *star*"


def test_real_emphasis_still_renders():
    assert rl("_a_ *b* **c** __d__ H~2~O x^2^") == \
        "<i>a</i> <i>b</i> <b>c</b> <b>d</b> H<sub>2</sub>O x<sup>2</sup>"
    assert rl("**bold `co_de`**") == '<b>bold <font name="Courier">co_de</font></b>'
