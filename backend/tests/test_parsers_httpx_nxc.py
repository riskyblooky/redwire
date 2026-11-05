"""Scanner-import parsers for httpx (JSONL) and NetExec/nxc (console + --log)."""

import json

import pytest

from utils.parsers import detect_and_parse

NXC_CONSOLE = b"""\
SMB         10.0.0.5        445    DC01             [*] Windows Server 2019 Standard 17763 x64 (name:DC01) (domain:lab.local) (signing:True) (SMBv1:False)
SMB         10.0.0.6        445    FS01             [*] Windows Server 2012 R2 Standard 9600 x64 (name:FS01) (domain:lab.local) (signing:False) (SMBv1:True) (Null Auth:True)
SMB         10.0.0.7        445    WS01             [*] Windows 10 Build 19041 x64 (name:WS01) (domain:lab.local) (signing:False) (SMBv1:False)
SMB         10.0.0.6        445    FS01             [+] lab.local\\svc_backup:Summer2025! (Pwn3d!)
SMB         10.0.0.7        445    WS01             [-] lab.local\\svc_backup:Summer2025! STATUS_LOGON_FAILURE
SMB         10.0.0.6        445    FS01             Share           Permissions     Remark
"""

NXC_LOG = b"""\
[2026-11-04 10:00:00]> /usr/bin/nxc rdp 10.0.0.0/24 -u admin -p Hunter2! --log nxc.log
2026-11-04 10:00:01 | rdp.py:120 - INFO - RDP         10.0.0.7        3389   WS01             [*] Windows 10 Build 19041 (name:WS01) (domain:lab.local) (nla:False)
2026-11-04 10:00:01 | ssh.py:60 - INFO - SSH         10.0.0.9        22     10.0.0.9         [*] SSH-2.0-OpenSSH_8.9p1 Ubuntu-3ubuntu0.1
"""


def _by_title(parsed):
    return {f.title: f for f in parsed.findings}


def test_nxc_console_hosts_ports_and_findings():
    p = detect_and_parse(NXC_CONSOLE, "smb_sweep.txt")
    assert p.source_tool == "nxc"
    assert [a.identifier for a in p.assets] == ["10.0.0.5", "10.0.0.6", "10.0.0.7"]
    assert [a.name for a in p.assets] == ["DC01", "FS01", "WS01"]
    dc = p.assets[0]
    assert [(x.port_number, x.service_name) for x in dc.ports] == [(445, "smb")]
    assert dc.ports[0].version == "Windows Server 2019 Standard 17763 x64"
    assert "domain:lab.local" in dc.description

    f = _by_title(p)
    assert set(f) == {"SMB Signing Not Required", "SMBv1 Enabled", "SMB Null Session Allowed"}
    assert sorted(f["SMB Signing Not Required"].affected_asset_indices) == [1, 2]
    assert f["SMBv1 Enabled"].affected_asset_indices == [1]
    assert f["SMB Null Session Allowed"].affected_asset_indices == [1]

    # Credential lines are skipped (and never land in any text field).
    assert any("credential" in w for w in p.warnings)
    blob = json.dumps([a.description for a in p.assets] + [x.description for x in p.findings])
    assert "Summer2025" not in blob


def test_nxc_log_file_prefix_and_command_redacted():
    p = detect_and_parse(NXC_LOG, "nxc.log")
    assert p.source_tool == "nxc"
    assert {a.identifier for a in p.assets} == {"10.0.0.7", "10.0.0.9"}
    assert _by_title(p)["RDP Network Level Authentication Not Required"].severity == "LOW"
    ssh = next(a for a in p.assets if a.identifier == "10.0.0.9")
    assert ssh.name == "10.0.0.9" and ssh.ports[0].version.startswith("SSH-2.0-OpenSSH_8.9p1")
    assert "Hunter2" not in p.raw_metadata["command"] and "-p ****" in p.raw_metadata["command"]


def test_unrecognised_text_rejected():
    with pytest.raises(ValueError):
        detect_and_parse(b"just some notes\nnothing to see", "notes.txt")


HTTPX_NEW = [
    {"timestamp": "2026-11-04T10:00:00Z", "url": "https://app.example.com", "input": "app.example.com",
     "host": "93.184.216.34", "port": "443", "scheme": "https", "title": "Login", "status_code": 200,
     "webserver": "nginx/1.24.0", "tech": ["Nginx:1.24.0", "React"], "a": ["93.184.216.34"]},
    {"url": "http://app.example.com:8080", "input": "app.example.com", "port": "8080", "scheme": "http",
     "status_code": 302, "webserver": "Jetty(9.4.z)"},
    {"url": "http://10.0.0.20", "port": "80", "scheme": "http", "status_code": 403, "title": "Forbidden"},
]
HTTPX_OLD = [{"url": "https://legacy.example.com", "status-code": 200, "content-length": 512,
              "technologies": ["IIS:10.0"], "webserver": "Microsoft-IIS/10.0"}]


def _jsonl(rows):
    return "\n".join(json.dumps(r) for r in rows).encode()


def test_httpx_jsonl_assets_ports():
    p = detect_and_parse(_jsonl(HTTPX_NEW), "httpx.jsonl")
    assert p.source_tool == "httpx"
    assert not p.findings
    app, ip = p.assets
    assert (app.identifier, app.asset_type) == ("app.example.com", "Domain")
    assert [(x.port_number, x.service_name, x.version) for x in app.ports] == [
        (443, "https", "nginx/1.24.0"), (8080, "http", "Jetty(9.4.z)")]
    assert "Login" in app.description and "React" in app.description and "93.184.216.34" in app.description
    assert (ip.identifier, ip.asset_type, ip.ports[0].port_number) == ("10.0.0.20", "IP Address", 80)


def test_httpx_old_field_names_and_json_array():
    p = detect_and_parse(json.dumps(HTTPX_OLD).encode(), "out.json")
    assert p.source_tool == "httpx"
    assert "— 200" in p.assets[0].description and "IIS:10.0" in p.assets[0].description


def test_nuclei_still_detected():
    row = {"template-id": "tech-detect", "info": {"name": "Tech", "severity": "info"},
           "host": "https://a.example.com", "matched-at": "https://a.example.com"}
    assert detect_and_parse(_jsonl([row]), "nuclei.jsonl").source_tool == "nuclei"
