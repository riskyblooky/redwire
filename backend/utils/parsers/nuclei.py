"""
utils/parsers/nuclei.py — Nuclei JSONL Output Parser

Parses Nuclei results in JSON or JSONL format (one result per line).
Each object represents a single template match, which maps to one finding.
Findings are deduplicated by template ID (merging affected hosts).
"""

import json
from urllib.parse import urlparse
from typing import Optional
from utils.parsers import (
    ParsedImportData, ParsedAsset, ParsedFinding, ParsedPort,
)

# Nuclei severity → RedWire severity
_SEVERITY_MAP = {
    "critical": "CRITICAL",
    "high": "HIGH",
    "medium": "MEDIUM",
    "low": "LOW",
    "info": "INFO",
    "unknown": "INFO",
}


def _extract_host(host_str: str) -> tuple[str, str, Optional[int]]:
    """
    Extract (identifier, asset_type, port) from a Nuclei host string.
    Nuclei hosts can be IPs, domains, or full URLs.
    """
    if not host_str:
        return ("unknown", "Other", None)

    # If it looks like a URL (has scheme)
    if "://" in host_str:
        try:
            parsed = urlparse(host_str)
            hostname = parsed.hostname or host_str
            port = parsed.port
            return (hostname, "URL", port)
        except Exception:
            pass

    # Might be IP:port
    if ":" in host_str:
        parts = host_str.rsplit(":", 1)
        try:
            port = int(parts[1])
            return (parts[0], "IP Address", port)
        except (ValueError, IndexError):
            pass

    # Plain hostname or IP
    # Simple heuristic: if it's all digits and dots, it's an IP
    if all(c in "0123456789." for c in host_str):
        return (host_str, "IP Address", None)

    return (host_str, "Domain", None)


def parse(content: bytes) -> ParsedImportData:
    """Parse Nuclei JSON/JSONL output into ParsedImportData."""
    result = ParsedImportData(source_tool="nuclei")

    text = content.decode("utf-8", errors="ignore").strip()
    if not text:
        result.warnings.append("Empty file.")
        return result

    # Parse lines — support both single JSON object/array and JSONL
    items = []
    if text.startswith("["):
        # JSON array
        try:
            items = json.loads(text)
        except json.JSONDecodeError as e:
            result.warnings.append(f"JSON parse error: {e}")
            return result
    else:
        # JSONL (one JSON object per line)
        for line_num, line in enumerate(text.splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                result.warnings.append(f"Skipped invalid JSON on line {line_num}")

    if not items:
        result.warnings.append("No valid results found.")
        return result

    result.raw_metadata["total_results"] = len(items)

    # Track assets and findings for dedup
    asset_index: dict[str, int] = {}           # host_identifier -> index
    finding_dedup: dict[str, int] = {}          # template_id -> finding index

    for item in items:
        if not isinstance(item, dict):
            continue

        # Extract host
        host_str = item.get("host", "") or item.get("matched-at", "") or ""
        identifier, asset_type, port = _extract_host(host_str)

        # Create or find asset
        if identifier not in asset_index:
            asset = ParsedAsset(
                name=identifier,
                asset_type=asset_type,
                identifier=identifier,
                description=f"Imported from Nuclei scan",
            )
            if port:
                svc = None
                if port == 80:
                    svc = "http"
                elif port == 443:
                    svc = "https"
                elif port == 22:
                    svc = "ssh"
                elif port == 21:
                    svc = "ftp"
                asset.ports.append(ParsedPort(
                    port_number=port,
                    protocol="TCP",
                    service_name=svc,
                    state="OPEN",
                ))

            asset_index[identifier] = len(result.assets)
            result.assets.append(asset)

        asset_idx = asset_index[identifier]

        # Extract finding info
        info = item.get("info", {}) or {}
        template_id = item.get("template-id", "") or item.get("templateID", "") or ""
        template_name = info.get("name", "") or template_id or "Unknown"
        severity_raw = (info.get("severity", "") or "info").lower()
        severity = _SEVERITY_MAP.get(severity_raw, "INFO")

        # Description
        desc = info.get("description", "")
        matcher_name = item.get("matcher-name", "")
        matched_at = item.get("matched-at", "")
        extracted_results = item.get("extracted-results", []) or []

        desc_parts = []
        if desc:
            desc_parts.append(desc)
        if matched_at:
            desc_parts.append(f"**Matched at**: `{matched_at}`")
        if matcher_name:
            desc_parts.append(f"**Matcher**: `{matcher_name}`")
        if extracted_results:
            desc_parts.append("**Extracted**:\n" + "\n".join(f"- `{r}`" for r in extracted_results))

        description = "\n\n".join(desc_parts) if desc_parts else f"Nuclei template: {template_id}"

        # References
        refs = info.get("reference", []) or []
        if isinstance(refs, str):
            refs = [refs]
        refs_str = "\n".join(r for r in refs if r) if refs else None

        # CVSS
        classification = info.get("classification", {}) or {}
        cvss_score = None
        cvss_metrics = classification.get("cvss-metrics") or classification.get("cvss-score")
        cvss_score_val = classification.get("cvss-score")
        if cvss_score_val:
            try:
                cvss_score = float(cvss_score_val)
            except (ValueError, TypeError):
                pass

        # Remediation
        remediation = info.get("remediation", "")

        # Tags as category
        tags = info.get("tags", []) or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",")]
        category = tags[0] if tags else None

        # Dedup by template_id (merge hosts)
        if template_id and template_id in finding_dedup:
            existing_idx = finding_dedup[template_id]
            if asset_idx not in result.findings[existing_idx].affected_asset_indices:
                result.findings[existing_idx].affected_asset_indices.append(asset_idx)
        else:
            finding = ParsedFinding(
                title=template_name,
                severity=severity,
                description=description,
                mitigations=remediation if remediation else None,
                references=refs_str,
                cvss_score=cvss_score,
                cvss_vector=str(cvss_metrics) if cvss_metrics else None,
                category=category,
                affected_asset_indices=[asset_idx],
            )
            dedup_key = template_id or f"{template_name}_{len(result.findings)}"
            finding_dedup[dedup_key] = len(result.findings)
            result.findings.append(finding)

    result.raw_metadata["total_hosts"] = len(result.assets)
    result.raw_metadata["unique_templates"] = len(result.findings)

    return result
