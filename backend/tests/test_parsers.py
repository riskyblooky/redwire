"""Scanner-import parser coverage — utils/parsers/{nmap,nessus,burp,nuclei}.

Each parser normalises a scanner's native output (XML / JSONL) into the
shared ``ParsedImportData`` shape (assets + ports + findings). These tests
feed a small representative sample of each format inline and pin:

  - source_tool + top-level counts
  - key field extraction (title, identifier, ports, severity)
  - severity mapping (native → RedWire UPPERCASE enum values)
  - dedup semantics (findings merged across hosts by plugin/template/name)
  - malformed / empty input → graceful degradation (warnings, no crash)

They also exercise ``detect_and_parse`` dispatch (extension + content sniff).

Pure-unit: no DB, no network. defusedxml is used by the parsers, so the
XML samples are also a smoke test that entity expansion stays disabled.
"""

from __future__ import annotations

import pytest

from utils.parsers import (
    detect_and_parse,
    ParsedImportData,
)
from utils.parsers import nmap as nmap_parser
from utils.parsers import nessus as nessus_parser
from utils.parsers import burp as burp_parser
from utils.parsers import nuclei as nuclei_parser


def test_nessus_and_burp_parsers_import_cleanly():
    """Regression pin: both modules must stay importable.

    They annotate helper params as ``Optional[ET.Element]`` where
    ``ET = defusedxml.ElementTree`` (which does not export ``Element``). Only
    ``from __future__ import annotations`` in each module keeps that hint from
    being evaluated at import time and crashing the whole parser — and with it
    every .nessus / Burp .xml upload through ``detect_and_parse``. Importing
    the modules at the top of this file already exercises this; assert the
    guard is present so a refactor that drops it fails loudly here.
    """
    import pathlib

    for mod in (nessus_parser, burp_parser):
        src = pathlib.Path(mod.__file__).read_text()
        assert "from __future__ import annotations" in src, (
            f"{mod.__name__}: lost future-annotations guard — Optional[ET.Element] "
            f"will crash the module at import time again"
        )


def _b(s: str) -> bytes:
    return s.encode("utf-8")


# ═══════════════════════════════════════════════════════════════════
# Nmap
# ═══════════════════════════════════════════════════════════════════

_NMAP_XML = """<?xml version="1.0"?>
<nmaprun scanner="nmap" args="nmap -sV 10.0.0.5" startstr="Mon">
  <host>
    <status state="up"/>
    <address addr="10.0.0.5" addrtype="ipv4"/>
    <address addr="AA:BB:CC:DD:EE:FF" addrtype="mac"/>
    <hostnames><hostname name="web01.corp"/></hostnames>
    <os><osmatch name="Linux 5.x" accuracy="97"/></os>
    <ports>
      <port protocol="tcp" portid="443">
        <state state="open"/>
        <service name="https" product="nginx" version="1.24.0"/>
      </port>
      <port protocol="udp" portid="53">
        <state state="open|filtered"/>
        <service name="domain"/>
      </port>
      <port protocol="tcp" portid="99999">
        <state state="open"/>
      </port>
    </ports>
  </host>
  <host>
    <status state="down"/>
    <address addr="10.0.0.6" addrtype="ipv4"/>
  </host>
</nmaprun>"""


def test_nmap_basic_asset_and_ports():
    r = nmap_parser.parse(_b(_NMAP_XML))
    assert r.source_tool == "nmap"
    # Down host is skipped; only the up host becomes an asset.
    assert len(r.assets) == 1
    a = r.assets[0]
    # Hostname wins for display name; identifier is the raw IP.
    assert a.name == "web01.corp"
    assert a.identifier == "10.0.0.5"
    assert a.asset_type == "IP Address"
    assert "OS: Linux 5.x (accuracy: 97%)" in a.description
    assert "MAC: AA:BB:CC:DD:EE:FF" in a.description


def test_nmap_port_parsing_and_filtering():
    r = nmap_parser.parse(_b(_NMAP_XML))
    a = r.assets[0]
    ports = {(p.port_number, p.protocol): p for p in a.ports}
    # Out-of-range 99999 dropped; 443 tcp and 53 udp survive.
    assert (99999, "TCP") not in ports and (99999, "UDP") not in ports
    p443 = ports[(443, "TCP")]
    assert p443.service_name == "https"
    assert p443.version == "nginx 1.24.0"
    assert p443.state == "OPEN"
    p53 = ports[(53, "UDP")]
    assert p53.protocol == "UDP"
    # "open|filtered" contains OPEN → normalised to OPEN.
    assert p53.state == "OPEN"


def test_nmap_produces_no_findings():
    # Nmap is a port scanner, not a vuln scanner.
    r = nmap_parser.parse(_b(_NMAP_XML))
    assert r.findings == []
    assert r.raw_metadata["total_hosts"] == 1


def test_nmap_malformed_xml_is_graceful():
    r = nmap_parser.parse(b"<nmaprun><host>oops")
    assert isinstance(r, ParsedImportData)
    assert r.assets == []
    assert any("XML parse error" in w for w in r.warnings)


# ═══════════════════════════════════════════════════════════════════
# Nessus
# ═══════════════════════════════════════════════════════════════════

_NESSUS_XML = """<?xml version="1.0"?>
<NessusClientData_v2>
  <Policy><policyName>Full Scan</policyName></Policy>
  <Report name="Weekly">
    <ReportHost name="10.0.0.10">
      <HostProperties>
        <tag name="host-ip">10.0.0.10</tag>
        <tag name="host-fqdn">db01.corp</tag>
        <tag name="operating-system">Windows Server 2019</tag>
      </HostProperties>
      <ReportItem port="0" protocol="tcp" svc_name="general" pluginID="0" pluginName="Ping" severity="0"/>
      <ReportItem port="445" protocol="tcp" svc_name="cifs" pluginID="12345"
                  pluginName="SMB Signing Disabled" severity="2" pluginFamily="Windows">
        <risk_factor>Medium</risk_factor>
        <synopsis>Signing not required.</synopsis>
        <description>The remote SMB server does not require signing.</description>
        <solution>Enforce SMB signing.</solution>
        <cvss3_base_score>5.3</cvss3_base_score>
        <cvss3_vector>CVSS:3.0/AV:N</cvss3_vector>
        <cvss_base_score>4.3</cvss_base_score>
        <cve>CVE-2020-1234</cve>
        <see_also>https://example.com/kb</see_also>
      </ReportItem>
    </ReportHost>
    <ReportHost name="10.0.0.11">
      <HostProperties>
        <tag name="host-ip">10.0.0.11</tag>
      </HostProperties>
      <ReportItem port="445" protocol="tcp" svc_name="cifs" pluginID="12345"
                  pluginName="SMB Signing Disabled" severity="2" pluginFamily="Windows">
        <risk_factor>Medium</risk_factor>
        <description>Same plugin, second host.</description>
      </ReportItem>
    </ReportHost>
  </Report>
</NessusClientData_v2>"""


def test_nessus_assets_and_metadata():
    r = nessus_parser.parse(_b(_NESSUS_XML))
    assert r.source_tool == "nessus"
    assert r.raw_metadata["policy_name"] == "Full Scan"
    assert r.raw_metadata["report_name"] == "Weekly"
    assert len(r.assets) == 2
    a0 = r.assets[0]
    assert a0.name == "db01.corp"          # FQDN wins for display
    assert a0.identifier == "10.0.0.10"     # host-ip is the identifier
    assert "OS: Windows Server 2019" in a0.description


def test_nessus_finding_fields_and_cvss_prefers_v3():
    r = nessus_parser.parse(_b(_NESSUS_XML))
    findings = [f for f in r.findings if f.title == "SMB Signing Disabled"]
    assert len(findings) == 1
    f = findings[0]
    assert f.severity == "MEDIUM"           # risk_factor "Medium" → MEDIUM
    assert f.cvss_score == 5.3              # CVSS3 preferred over CVSS2
    assert f.cvss_vector == "CVSS:3.0/AV:N"
    assert "CVE-2020-1234" in (f.references or "")
    assert "https://example.com/kb" in (f.references or "")
    assert f.category == "Windows"
    assert f.mitigations == "Enforce SMB signing."


def test_nessus_dedup_merges_affected_hosts():
    r = nessus_parser.parse(_b(_NESSUS_XML))
    f = next(f for f in r.findings if f.title == "SMB Signing Disabled")
    # Same pluginID across two hosts → one finding affecting two assets.
    assert sorted(f.affected_asset_indices) == [0, 1]
    assert r.raw_metadata["total_plugins"] == 1


def test_nessus_plugin_zero_is_not_a_finding_but_ports_still_tracked():
    r = nessus_parser.parse(_b(_NESSUS_XML))
    # pluginID 0 (port-scanner metadata) never becomes a finding.
    assert all("Ping" not in f.title for f in r.findings)
    # But the real port 445 got attached to the asset.
    assert any(p.port_number == 445 for p in r.assets[0].ports)


def test_nessus_malformed_xml_is_graceful():
    r = nessus_parser.parse(b"<NessusClientData_v2><broken")
    assert r.assets == [] and r.findings == []
    assert any("XML parse error" in w for w in r.warnings)


# ═══════════════════════════════════════════════════════════════════
# Burp
# ═══════════════════════════════════════════════════════════════════

_BURP_XML = """<?xml version="1.0"?>
<issues>
  <issue>
    <name>Cross-site scripting (reflected)</name>
    <host ip="10.0.0.20">https://shop.example.com</host>
    <path>/search</path>
    <location>/search parameter q</location>
    <severity>High</severity>
    <confidence>Certain</confidence>
    <issueBackground>&lt;p&gt;XSS lets an attacker run script.&lt;/p&gt;</issueBackground>
    <issueDetail>The value of the &lt;b&gt;q&lt;/b&gt; parameter is reflected.</issueDetail>
    <remediationBackground>Encode output.</remediationBackground>
    <references>
      <reference><url>https://portswigger.net/xss</url></reference>
    </references>
  </issue>
  <issue>
    <name>Cross-site scripting (reflected)</name>
    <host ip="10.0.0.21">https://api.example.com</host>
    <path>/q</path>
    <severity>High</severity>
  </issue>
  <issue>
    <name>Information disclosure</name>
    <host ip="10.0.0.20">https://shop.example.com</host>
    <severity>Information</severity>
  </issue>
</issues>"""


def test_burp_findings_and_severity_map():
    r = burp_parser.parse(_b(_BURP_XML))
    assert r.source_tool == "burp"
    titles = {f.title for f in r.findings}
    assert "Cross-site scripting (reflected)" in titles
    xss = next(f for f in r.findings if f.title.startswith("Cross-site"))
    assert xss.severity == "HIGH"
    info = next(f for f in r.findings if f.title == "Information disclosure")
    assert info.severity == "INFO"           # "Information" → INFO
    assert info.category == "Web Application"


def test_burp_html_is_stripped_to_markdown():
    r = burp_parser.parse(_b(_BURP_XML))
    xss = next(f for f in r.findings if f.title.startswith("Cross-site"))
    # <b>q</b> → **q**, and <p> tags decoded+stripped; no raw tags left.
    assert "<b>" not in xss.description and "<p>" not in xss.description
    assert "**q**" in xss.description
    assert "https://portswigger.net/xss" in (xss.references or "")


def test_burp_dedup_merges_hosts_by_issue_name():
    r = burp_parser.parse(_b(_BURP_XML))
    xss = next(f for f in r.findings if f.title.startswith("Cross-site"))
    # Same issue name on two different hosts → one finding, two assets.
    assert len(xss.affected_asset_indices) == 2
    assert r.raw_metadata["total_issues"] == 3


def test_burp_no_issues_warns():
    r = burp_parser.parse(_b("<issues></issues>"))
    assert r.findings == []
    assert any("No <issue>" in w for w in r.warnings)


def test_burp_malformed_xml_is_graceful():
    r = burp_parser.parse(b"<issues><issue>oops")
    assert any("XML parse error" in w for w in r.warnings)


# ═══════════════════════════════════════════════════════════════════
# Nuclei
# ═══════════════════════════════════════════════════════════════════

_NUCLEI_JSONL = (
    '{"template-id":"CVE-2021-1234","host":"https://web.example.com:8443",'
    '"matched-at":"https://web.example.com:8443/x",'
    '"info":{"name":"Example RCE","severity":"critical",'
    '"description":"Remote code execution.","tags":["cve","rce"],'
    '"reference":["https://nvd.example/CVE-2021-1234"],'
    '"classification":{"cvss-score":9.8,"cvss-metrics":"CVSS:3.1/AV:N"},'
    '"remediation":"Patch now."}}\n'
    '{"template-id":"CVE-2021-1234","host":"https://api.example.com",'
    '"info":{"name":"Example RCE","severity":"critical"}}\n'
    '{"template-id":"tech-detect","host":"10.0.0.30:22",'
    '"info":{"name":"SSH detected","severity":"info"}}\n'
    'not-valid-json-line\n'
)


def test_nuclei_jsonl_parsing_and_severity():
    r = nuclei_parser.parse(_b(_NUCLEI_JSONL))
    assert r.source_tool == "nuclei"
    rce = next(f for f in r.findings if f.title == "Example RCE")
    assert rce.severity == "CRITICAL"
    assert rce.cvss_score == 9.8
    assert rce.cvss_vector == "CVSS:3.1/AV:N"
    assert rce.category == "cve"             # first tag
    assert rce.mitigations == "Patch now."
    assert "https://nvd.example/CVE-2021-1234" in (rce.references or "")


def test_nuclei_host_extraction_variants():
    r = nuclei_parser.parse(_b(_NUCLEI_JSONL))
    by_id = {a.identifier: a for a in r.assets}
    # URL host → hostname only, port 8443 attached.
    assert "web.example.com" in by_id
    web = by_id["web.example.com"]
    assert web.asset_type == "URL"
    assert any(p.port_number == 8443 for p in web.ports)
    # IP:port → IP identifier + port, ssh service label.
    assert "10.0.0.30" in by_id
    ip = by_id["10.0.0.30"]
    assert ip.asset_type == "IP Address"
    ssh_port = next(p for p in ip.ports if p.port_number == 22)
    assert ssh_port.service_name == "ssh"


def test_nuclei_dedup_by_template_and_bad_line_warned():
    r = nuclei_parser.parse(_b(_NUCLEI_JSONL))
    rce = next(f for f in r.findings if f.title == "Example RCE")
    # Same template-id on two hosts → one finding, two assets.
    assert len(rce.affected_asset_indices) == 2
    assert any("invalid JSON" in w.lower() or "Skipped invalid JSON" in w for w in r.warnings)


def test_nuclei_json_array_form():
    arr = '[{"template-id":"t1","host":"example.org","info":{"name":"Low thing","severity":"low"}}]'
    r = nuclei_parser.parse(_b(arr))
    assert len(r.findings) == 1
    assert r.findings[0].severity == "LOW"
    # Plain hostname (non-numeric) → Domain.
    assert r.assets[0].asset_type == "Domain"


def test_nuclei_empty_input_warns():
    r = nuclei_parser.parse(b"   ")
    assert r.findings == []
    assert any("Empty file" in w for w in r.warnings)


def test_nuclei_malformed_json_array_warns():
    r = nuclei_parser.parse(_b("[ this is not json"))
    assert r.findings == []
    assert any("JSON parse error" in w for w in r.warnings)


# ═══════════════════════════════════════════════════════════════════
# detect_and_parse dispatch
# ═══════════════════════════════════════════════════════════════════


def test_detect_nessus_by_extension():
    r = detect_and_parse(_b(_NESSUS_XML), "scan.nessus")
    assert r.source_tool == "nessus"


def test_detect_burp_vs_nmap_by_content_sniff():
    burp = detect_and_parse(_b(_BURP_XML), "export.xml")
    nmap = detect_and_parse(_b(_NMAP_XML), "scan.xml")
    assert burp.source_tool == "burp"
    assert nmap.source_tool == "nmap"


def test_detect_nuclei_by_json_extension():
    r = detect_and_parse(_b(_NUCLEI_JSONL), "results.jsonl")
    assert r.source_tool == "nuclei"


def test_detect_unsupported_extension_raises():
    with pytest.raises(ValueError):
        detect_and_parse(b"whatever", "report.pdf")
