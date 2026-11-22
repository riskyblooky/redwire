"""Smaller parser fixes: nuclei vector / IPv6 / extra ports, nmap
closed|filtered, httpx out-of-range port, non-UTF-8 asset CSV."""

from __future__ import annotations

import json

from utils.parsers import httpx as httpx_parser, nmap, nuclei


def _nuclei(*items):
    return nuclei.parse("\n".join(json.dumps(i) for i in items).encode())


def test_nuclei_score_is_not_a_vector():
    r = _nuclei({"template-id": "t1", "host": "10.0.0.1", "info": {
        "name": "X", "severity": "high", "classification": {"cvss-score": 9.8}}})
    assert r.findings[0].cvss_score == 9.8 and r.findings[0].cvss_vector is None


def test_nuclei_ipv6_and_every_port_kept():
    r = _nuclei(
        {"template-id": "a", "host": "2001:db8::1", "info": {"name": "A", "severity": "low"}},
        {"template-id": "b", "host": "[2001:db8::2]:8443", "info": {"name": "B", "severity": "low"}},
        {"template-id": "c", "host": "10.0.0.9:80", "info": {"name": "C", "severity": "low"}},
        {"template-id": "d", "host": "10.0.0.9:443", "info": {"name": "D", "severity": "low"}},
    )
    by = {a.identifier: sorted(p.port_number for p in a.ports) for a in r.assets}
    assert by == {"2001:db8::1": [], "2001:db8::2": [8443], "10.0.0.9": [80, 443]}


def test_nmap_closed_filtered_is_not_open():
    xml = b"""<?xml version="1.0"?><nmaprun><host><status state="up"/>
<address addr="10.0.0.2" addrtype="ipv4"/><ports>
<port protocol="tcp" portid="22"><state state="closed|filtered"/></port>
<port protocol="udp" portid="53"><state state="open|filtered"/></port>
</ports></host></nmaprun>"""
    ports = {p.port_number: p.state for p in nmap.parse(xml).assets[0].ports}
    assert ports == {22: "FILTERED", 53: "OPEN"}


def test_httpx_out_of_range_port_does_not_raise():
    line = json.dumps({"url": "http://example.test:99999/", "status_code": 200})
    r = httpx_parser.parse(line.encode())
    assert [a.name for a in r.assets] == ["example.test"]


def test_asset_csv_windows_1252():
    from routers.assets import _parse_csv_rows
    rows = _parse_csv_rows("name,identifier\nCafé,10.0.0.1\n".encode("cp1252"))
    assert rows[0]["name"] == "Café"
