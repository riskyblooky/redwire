"""Golden-file tests for the scanner parsers. Each fixture under
tests/fixtures/parsers is realistic output of its tool (full document
structure, the edge cases each format really has: DOCTYPEs, CDATA, mixed
field spellings, bad lines, down hosts, out-of-range ports) and is parsed
the way an import parses it. The whole result (every asset, port, finding,
instance, warning and metadata key) is compared with the checked-in
<fixture>.golden.json, so any change to what a parser extracts shows up as
a diff to review.

After an intended parser change, regenerate and review the diff:

    UPDATE_GOLDEN=1 python -m pytest tests/test_parser_golden.py
"""

from __future__ import annotations

import dataclasses
import enum
import json
import os
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "parsers"
UPDATE = os.getenv("UPDATE_GOLDEN") == "1"


def _jsonable(obj):
    if dataclasses.is_dataclass(obj):
        return {k: _jsonable(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, enum.Enum):
        return obj.value
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    return obj


def _check(result, golden: Path):
    got = json.dumps(_jsonable(result), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if UPDATE or not golden.exists():
        golden.write_text(got, encoding="utf-8")
        if not UPDATE:
            pytest.fail(f"wrote missing golden {golden.name}; review it and re-run")
        return
    assert got == golden.read_text(encoding="utf-8"), (
        f"{golden.name} differs; if the change is intended, regenerate with UPDATE_GOLDEN=1 and review the diff")


IMPORT_FIXTURES = {
    "nmap_sV_O.xml": "nmap",
    "internal_basic.nessus": "nessus",
    "burp_issues.xml": "burp",
    "nuclei_scan.jsonl": "nuclei",
    "httpx_probe.jsonl": "httpx",
    "nxc_smb_spray.log": "nxc",
}


@pytest.mark.parametrize("name,tool", sorted(IMPORT_FIXTURES.items()))
def test_scan_import_parse_matches_golden(name, tool):
    from utils.parsers import detect_and_parse
    result = detect_and_parse((FIXTURES / name).read_bytes(), name)
    assert result.source_tool == tool, "detected as the wrong tool"
    assert result.assets, "a realistic fixture yields assets"
    _check(result, FIXTURES / f"{name}.golden.json")


def test_asset_import_nmap_matches_golden():
    """The asset importer's nmap path (POST /assets/import with an .xml)."""
    from routers.assets import _parse_nmap_xml
    _check(_parse_nmap_xml((FIXTURES / "nmap_sV_O.xml").read_bytes()), FIXTURES / "nmap_sV_O.xml.asset_import.golden.json")


def test_spray_campaign_parse_matches_golden():
    """The password-spray importer's view of the same nxc log."""
    from utils.parsers.netexec import parse_netexec_log
    _check(parse_netexec_log((FIXTURES / "nxc_smb_spray.log").read_text()), FIXTURES / "nxc_smb_spray.log.spray.golden.json")


def test_every_fixture_has_a_test():
    inputs = {p.name for p in FIXTURES.iterdir() if not p.name.endswith(".golden.json")}
    assert inputs == set(IMPORT_FIXTURES), "a fixture without a test, or a test without a fixture"


def test_burp_links_only_for_http_targets():
    from utils.parsers.burp import _strip_html
    assert _strip_html('<a href="https://x.test/a">A</a>') == "[A](https://x.test/a)"
    assert _strip_html('<a href="javascript:alert(1)">click</a>') == "click"
    assert _strip_html("intro:<ul><li>one</li><li>two</li></ul>after") == "intro:\n- one\n- two\nafter"
