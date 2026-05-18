"""
utils/parsers/burp.py — Burp Suite XML Export Parser

Parses Burp Suite XML issue export files.
Extracts issues → findings and host/URL → assets.
"""

import defusedxml.ElementTree as ET
import html
import re
from typing import Optional
from utils.parsers import (
    ParsedImportData, ParsedAsset, ParsedFinding, ParsedPort,
)

# Burp severity → RedWire severity
_SEVERITY_MAP = {
    "high": "HIGH",
    "medium": "MEDIUM",
    "low": "LOW",
    "information": "INFO",
    "info": "INFO",
}


def _strip_html(text: str) -> str:
    """Remove HTML tags and decode entities for clean markdown output."""
    if not text:
        return ""
    # Decode HTML entities
    text = html.unescape(text)
    # Convert <br> and <p> to newlines
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?p\s*/?>", "\n", text, flags=re.IGNORECASE)
    # Convert <li> to bullet points
    text = re.sub(r"<li\s*>", "- ", text, flags=re.IGNORECASE)
    # Convert <b>/<strong> to bold
    text = re.sub(r"<(b|strong)>(.*?)</\1>", r"**\2**", text, flags=re.IGNORECASE | re.DOTALL)
    # Convert <code> to backticks
    text = re.sub(r"<code>(.*?)</code>", r"`\1`", text, flags=re.IGNORECASE | re.DOTALL)
    # Strip remaining HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Collapse multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _get_text(elem: Optional[ET.Element]) -> str:
    """Get text from element, stripping HTML."""
    if elem is None or elem.text is None:
        return ""
    return _strip_html(elem.text)


def _extract_host_info(url_str: str) -> tuple[str, str, Optional[int]]:
    """
    Extract (hostname, asset_type, port) from a URL string.
    Returns the hostname/IP, "URL" or "Domain", and optional port.
    """
    from urllib.parse import urlparse
    try:
        parsed = urlparse(url_str)
        host = parsed.hostname or url_str
        port = parsed.port
        return host, "URL", port
    except Exception:
        return url_str, "URL", None


def parse(content: bytes) -> ParsedImportData:
    """Parse a Burp Suite XML export into ParsedImportData."""
    result = ParsedImportData(source_tool="burp")

    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        result.warnings.append(f"XML parse error: {e}")
        return result

    # Burp exports have <issues> root with <issue> children,
    # or sometimes just <issue> elements directly
    issues = root.findall(".//issue")
    if not issues:
        result.warnings.append("No <issue> elements found in Burp XML.")
        return result

    result.raw_metadata["total_issues"] = len(issues)

    # Track assets by host for dedup
    asset_index: dict[str, int] = {}  # host:port_key -> index

    # Track findings by type+host for dedup
    finding_dedup: dict[str, int] = {}  # type_name -> finding index

    for issue in issues:
        # Extract issue details
        issue_name = _get_text(issue.find("name")) or "Unknown Issue"
        severity_raw = _get_text(issue.find("severity")).lower()
        severity = _SEVERITY_MAP.get(severity_raw, "INFO")
        confidence = _get_text(issue.find("confidence"))

        # Host / URL info
        host_elem = issue.find("host")
        host_ip = ""
        host_url = ""
        if host_elem is not None:
            host_ip = host_elem.get("ip", "")
            host_url = host_elem.text or ""
        path = _get_text(issue.find("path"))
        location = _get_text(issue.find("location"))

        # Full URL
        full_url = host_url
        if path:
            full_url = host_url.rstrip("/") + "/" + path.lstrip("/")

        # Create or find asset
        if host_url:
            host_key = host_url
        elif host_ip:
            host_key = host_ip
        else:
            host_key = "unknown"

        if host_key not in asset_index:
            hostname, asset_type, port = _extract_host_info(host_url or host_ip)
            asset = ParsedAsset(
                name=hostname or host_key,
                asset_type=asset_type if host_url else "IP Address",
                identifier=host_ip or hostname or host_key,
                description=f"Imported from Burp Suite scan\nURL: {host_url}" if host_url else "Imported from Burp Suite scan",
            )
            # Add port if detected
            if port and port not in (80, 443):
                asset.ports.append(ParsedPort(
                    port_number=port,
                    protocol="TCP",
                    state="OPEN",
                ))
            elif port:
                svc = "https" if port == 443 else "http"
                asset.ports.append(ParsedPort(
                    port_number=port,
                    protocol="TCP",
                    service_name=svc,
                    state="OPEN",
                ))

            asset_index[host_key] = len(result.assets)
            result.assets.append(asset)

        asset_idx = asset_index[host_key]

        # Extract issue content
        issue_background = _get_text(issue.find("issueBackground"))
        issue_detail = _get_text(issue.find("issueDetail"))
        remediation_bg = _get_text(issue.find("remediationBackground"))
        remediation_detail = _get_text(issue.find("remediationDetail"))

        # Build description
        desc_parts = []
        if issue_detail:
            desc_parts.append(issue_detail)
        if issue_background:
            desc_parts.append(f"**Background**: {issue_background}")
        if location:
            desc_parts.append(f"**Location**: {location}")
        if full_url:
            desc_parts.append(f"**URL**: `{full_url}`")
        if confidence:
            desc_parts.append(f"**Confidence**: {confidence}")

        description = "\n\n".join(desc_parts) if desc_parts else f"Burp issue: {issue_name}"

        # Build mitigations
        mitigation_parts = []
        if remediation_detail:
            mitigation_parts.append(remediation_detail)
        if remediation_bg:
            mitigation_parts.append(remediation_bg)
        mitigations = "\n\n".join(mitigation_parts) if mitigation_parts else None

        # References
        refs = []
        for ref_elem in issue.findall(".//reference"):
            ref_url = _get_text(ref_elem.find("url"))
            if ref_url:
                refs.append(ref_url)

        # Vulnerability classifications
        vuln_classifications = _get_text(issue.find("vulnerabilityClassifications"))
        if vuln_classifications:
            refs.append(vuln_classifications)

        # Dedup by issue type (merge affected hosts)
        dedup_key = issue_name
        if dedup_key in finding_dedup:
            existing_idx = finding_dedup[dedup_key]
            if asset_idx not in result.findings[existing_idx].affected_asset_indices:
                result.findings[existing_idx].affected_asset_indices.append(asset_idx)
        else:
            finding = ParsedFinding(
                title=issue_name,
                severity=severity,
                description=description,
                impact=issue_background or None,
                mitigations=mitigations,
                references="\n".join(refs) if refs else None,
                category="Web Application",
                affected_asset_indices=[asset_idx],
            )
            finding_dedup[dedup_key] = len(result.findings)
            result.findings.append(finding)

    result.raw_metadata["total_hosts"] = len(result.assets)
    result.raw_metadata["unique_issue_types"] = len(result.findings)

    return result
