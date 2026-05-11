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
    source_tool: str             # "nessus", "burp", "nuclei", "nmap"
    assets: list[ParsedAsset] = field(default_factory=list)
    findings: list[ParsedFinding] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    raw_metadata: dict = field(default_factory=dict)


def detect_and_parse(content: bytes, filename: str) -> ParsedImportData:
    """
    Auto-detect the file format and parse with the appropriate parser.

    Supports:
      - .nessus          → Nessus XML
      - .xml             → Burp XML or Nmap XML (auto-detected by root element)
      - .json / .jsonl   → Nuclei JSONL
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
        from utils.parsers.nuclei import parse
        return parse(content)

    raise ValueError(f"Unsupported file format: {filename}")
