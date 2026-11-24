"""
utils/parsers — Scanner Output Parser Framework

Provides a standardised interface for parsing output from security
scanning tools (Nessus, Burp Suite, Nuclei, Nmap) into a common
data structure that the import router can commit to the database.

Each parser module exports a `parse(content: bytes) -> ParsedImportData`
function. The registry auto-detects the correct parser from file
extension and content sniffing.
"""

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ParsedPort:
    """A single port discovered on an asset."""
    port_number: int
    protocol: str = "TCP"       # TCP or UDP
    service_name: Optional[str] = None
    state: str = "OPEN"         # OPEN, CLOSED, FILTERED
    version: Optional[str] = None


@dataclass
class ParsedAsset:
    """An asset (host/domain/URL) extracted from scanner output."""
    name: str
    asset_type: str             # IP Address, Domain, URL, Server, etc.
    identifier: str             # The raw IP, hostname, or URL
    description: str = ""
    ports: list[ParsedPort] = field(default_factory=list)


@dataclass
class ParsedInstance:
    """One occurrence of a finding: where it was seen and what the scanner
    reported there (Nessus plugin output, Burp issue detail, Nuclei
    extracted values)."""
    asset_index: int
    location: Optional[str] = None
    detail: Optional[str] = None


@dataclass
class ParsedFinding:
    """A finding/vulnerability extracted from scanner output."""
    title: str
    severity: str               # CRITICAL, HIGH, MEDIUM, LOW, INFO
    description: str = ""
    impact: Optional[str] = None
    mitigations: Optional[str] = None
    references: Optional[str] = None
    cvss_score: Optional[float] = None
    cvss_vector: Optional[str] = None
    category: Optional[str] = None
    # Indices into the parent ParsedImportData.assets list
    affected_asset_indices: list[int] = field(default_factory=list)
    # Every occurrence, kept through the per-tool dedupe (which merges a
    # finding seen on several hosts into one).
    instances: list[ParsedInstance] = field(default_factory=list)


@dataclass
class ParsedImportData:
    """Unified output from any scanner parser."""
    source_tool: str             # "nessus", "burp", "nuclei", "nmap", "httpx", "nxc"
    assets: list[ParsedAsset] = field(default_factory=list)
    findings: list[ParsedFinding] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    raw_metadata: dict = field(default_factory=dict)


def _first_json_object(content: bytes) -> dict:
    """The first JSON object of a JSON array or JSONL file ({} if none)."""
    import json
    text = content[:65536].decode("utf-8", errors="ignore").lstrip()
    if text.startswith("["):
        try:
            data = json.loads(content.decode("utf-8", errors="ignore"))
            return data[0] if data and isinstance(data[0], dict) else {}
        except (ValueError, IndexError):
            return {}
    for line in text.splitlines():
        line = line.strip()
        if line:
            try:
                obj = json.loads(line)
                return obj if isinstance(obj, dict) else {}
            except ValueError:
                return {}
    return {}


_XML_PROLOG_RE = re.compile(
    r"\s*(?:<\?.*?\?>|<!--.*?-->|<!DOCTYPE(?:[^\[>]|\[.*?\])*>)", re.S | re.I)
_XML_ROOT_RE = re.compile(r"\s*<([A-Za-z_][\w.:-]*)")


def _xml_root_name(content: bytes, limit: int = 1 << 20) -> str:
    """Lower-cased name of the document's root element, skipping the XML
    declaration, comments and a DOCTYPE with its internal subset.

    Sniffing for "<issues" in the first 2 KB missed Burp exports, whose
    inline DTD runs past that, and sent them to the Nmap parser."""
    head = content[:limit]
    if head.startswith(b"\xff\xfe") or head.startswith(b"\xfe\xff"):
        text = head.decode("utf-16", errors="ignore")
    else:
        text = head.decode("utf-8", errors="ignore").lstrip("\ufeff")
    pos = 0
    while True:
        m = _XML_PROLOG_RE.match(text, pos)
        if not m or m.end() == pos:
            break
        pos = m.end()
    m = _XML_ROOT_RE.match(text, pos)
    return m.group(1).split(":")[-1].lower() if m else ""


def detect_and_parse(content: bytes, filename: str) -> ParsedImportData:
    """
    Auto-detect the file format and parse with the appropriate parser.

    Supports:
      - .nessus          → Nessus XML
      - .xml             → Burp XML or Nmap XML (auto-detected by root element)
      - .json / .jsonl   → Nuclei or httpx JSONL (sniffed from the first result)
      - .txt / .log      → NetExec (nxc) console or --log output
    """
    lower = filename.lower()

    if lower.endswith(".nessus"):
        from utils.parsers.nessus import parse
        return parse(content)

    if lower.endswith(".xml"):
        root = _xml_root_name(content)
        if root == "issues":
            from utils.parsers.burp import parse
        elif root == "nmaprun":
            from utils.parsers.nmap import parse
        elif root == "nessusclientdata_v2":
            from utils.parsers.nessus import parse
        else:
            raise ValueError(
                f"Unrecognised XML in {filename} (root element {root or 'not found'!r}; "
                "expected Burp <issues>, Nmap <nmaprun> or Nessus <NessusClientData_v2>)."
            )
        return parse(content)

    if lower.endswith(".json") or lower.endswith(".jsonl"):
        from utils.parsers.httpx import looks_like_httpx
        if looks_like_httpx(_first_json_object(content)):
            from utils.parsers.httpx import parse
        else:
            from utils.parsers.nuclei import parse
        return parse(content)

    if lower.endswith(".txt") or lower.endswith(".log"):
        from utils.parsers.netexec import looks_like_netexec, parse
        if looks_like_netexec(content.decode("utf-8", errors="ignore")):
            return parse(content)
        raise ValueError(f"Unrecognised text output in {filename} (expected NetExec / nxc output).")

    raise ValueError(f"Unsupported file format: {filename}")


_INSTANCE_DETAIL_CAP = 4000


def render_instances(instances: list[ParsedInstance], asset_labels: dict[int, str]) -> str:
    """Markdown list of a finding's per-host evidence, or "" when the
    instances carry nothing beyond the host (the host links say that)."""
    rows = [i for i in instances if i.location or i.detail]
    if not rows:
        return ""
    out = []
    for inst in rows:
        head = f"- `{asset_labels.get(inst.asset_index, '?')}`"
        if inst.location:
            head += f" — `{inst.location}`"
        out.append(head)
        if inst.detail:
            detail = inst.detail.strip()
            if len(detail) > _INSTANCE_DETAIL_CAP:
                detail = detail[:_INSTANCE_DETAIL_CAP] + "\n… (truncated)"
            fence = "````" if "```" in detail else "```"
            out.append(f"  {fence}\n" + "\n".join("  " + ln for ln in detail.splitlines()) + f"\n  {fence}")
    return "\n".join(out)
