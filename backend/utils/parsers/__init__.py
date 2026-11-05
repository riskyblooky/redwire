"""
utils/parsers — Scanner Output Parser Framework

Provides a standardised interface for parsing output from security
scanning tools (Nessus, Burp Suite, Nuclei, Nmap) into a common
data structure that the import router can commit to the database.

Each parser module exports a `parse(content: bytes) -> ParsedImportData`
function. The registry auto-detects the correct parser from file
extension and content sniffing.
"""

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
        # Sniff root element to distinguish Burp vs Nmap
        try:
            head = content[:2000].decode("utf-8", errors="ignore").lower()
        except Exception:
            head = ""

        if "<issues" in head or "<issue>" in head:
            from utils.parsers.burp import parse
            return parse(content)
        elif "<nmaprun" in head:
            from utils.parsers.nmap import parse
            return parse(content)
        else:
            # Try Nessus-style (NessusClientData_v2)
            if "<nessusclientdata_v2" in head or "<report " in head:
                from utils.parsers.nessus import parse
                return parse(content)
            # Fallback: try Nmap
            from utils.parsers.nmap import parse
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
