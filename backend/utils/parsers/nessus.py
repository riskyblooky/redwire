"""
utils/parsers/nessus.py — Tenable Nessus / OpenVAS XML Parser

Parses .nessus files (NessusClientData_v2 format).
Extracts hosts → assets+ports and plugin results → findings.
Deduplicates findings by plugin ID (merges affected hosts).
"""

import xml.etree.ElementTree as ET
from typing import Optional
from utils.parsers import (
    ParsedImportData, ParsedAsset, ParsedFinding, ParsedPort,
)

# Nessus risk_factor → RedWire severity
_SEVERITY_MAP = {
    "critical": "CRITICAL",
    "high": "HIGH",
    "medium": "MEDIUM",
    "low": "LOW",
    "none": "INFO",
}


def _clean_text(elem: Optional[ET.Element]) -> str:
    """Extract text from an XML element, stripping whitespace."""
    if elem is None or elem.text is None:
        return ""
    return elem.text.strip()


def _get_child_text(parent: ET.Element, tag: str) -> str:
    """Get stripped text of a direct child element."""
    child = parent.find(tag)
    return _clean_text(child)


def parse(content: bytes) -> ParsedImportData:
    """Parse a .nessus XML file into ParsedImportData."""
    result = ParsedImportData(source_tool="nessus")

    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        result.warnings.append(f"XML parse error: {e}")
        return result

    # Extract scan metadata
    policy = root.find(".//Policy/policyName")
    if policy is not None and policy.text:
        result.raw_metadata["policy_name"] = policy.text.strip()

    report = root.find(".//Report")
    if report is not None:
        result.raw_metadata["report_name"] = report.get("name", "")

    # Track assets by IP for dedup and index lookup
    asset_index: dict[str, int] = {}  # identifier -> index in result.assets

    # Track findings by plugin_id for dedup (merge affected hosts)
    finding_map: dict[str, ParsedFinding] = {}  # plugin_id -> finding

    for host_elem in root.findall(".//ReportHost"):
        host_name = host_elem.get("name", "").strip()
        if not host_name:
            continue

        # Get IP from properties if available
        ip_address = host_name
        hostname = None
        os_name = None

        props = host_elem.find("HostProperties")
        if props is not None:
            for tag_elem in props.findall("tag"):
                tag_name = tag_elem.get("name", "")
                tag_val = tag_elem.text or ""
                if tag_name == "host-ip":
                    ip_address = tag_val.strip()
                elif tag_name == "host-fqdn":
                    hostname = tag_val.strip()
                elif tag_name == "operating-system":
                    os_name = tag_val.strip()

        # Create or find asset
        identifier = ip_address
        if identifier not in asset_index:
            display_name = hostname or ip_address
            desc_parts = [f"Imported from Nessus scan"]
            if hostname and hostname != ip_address:
                desc_parts.append(f"Hostname: {hostname}")
            if os_name:
                desc_parts.append(f"OS: {os_name}")

            asset = ParsedAsset(
                name=display_name,
                asset_type="IP Address",
                identifier=identifier,
                description="\n".join(desc_parts),
            )
            asset_index[identifier] = len(result.assets)
            result.assets.append(asset)

        asset_idx = asset_index[identifier]
        current_asset = result.assets[asset_idx]

        # Process ReportItems (findings + ports)
        for item in host_elem.findall("ReportItem"):
            port_str = item.get("port", "0")
            protocol = item.get("protocol", "tcp").upper()
            svc_name = item.get("svc_name", "")
            plugin_id = item.get("pluginID", "0")
            plugin_name = item.get("pluginName", "")
            severity_num = item.get("severity", "0")

            # Add port to asset (if it's a real port)
            try:
                port_num = int(port_str)
            except ValueError:
                port_num = 0

            if port_num > 0 and port_num <= 65535:
                # Check if port already exists on this asset
                existing_ports = {
                    (p.port_number, p.protocol)
                    for p in current_asset.ports
                }
                port_proto = "UDP" if protocol == "UDP" else "TCP"
                if (port_num, port_proto) not in existing_ports:
                    current_asset.ports.append(ParsedPort(
                        port_number=port_num,
                        protocol=port_proto,
                        service_name=svc_name if svc_name and svc_name != "general" else None,
                        state="OPEN",
                    ))

            # Skip "None" severity (informational port scans, etc.)
            # Also skip plugin 0 (port scanner metadata)
            if plugin_id == "0":
                continue

            # Map severity
            risk_factor = _get_child_text(item, "risk_factor").lower()
            if not risk_factor:
                # Fall back to numeric severity
                sev_map = {"0": "INFO", "1": "LOW", "2": "MEDIUM", "3": "HIGH", "4": "CRITICAL"}
                severity = sev_map.get(severity_num, "INFO")
            else:
                severity = _SEVERITY_MAP.get(risk_factor, "INFO")

            # Skip informational items to reduce noise (optional)
            # Users can still import them via checkbox

            # Build or merge finding
            if plugin_id in finding_map:
                # Merge: add this asset to affected list
                existing_finding = finding_map[plugin_id]
                if asset_idx not in existing_finding.affected_asset_indices:
                    existing_finding.affected_asset_indices.append(asset_idx)
            else:
                # Extract details
                description = _get_child_text(item, "description")
                synopsis = _get_child_text(item, "synopsis")
                solution = _get_child_text(item, "solution")
                see_also = _get_child_text(item, "see_also")

                # CVSS
                cvss_score = None
                cvss_vector = None
                cvss3_score_text = _get_child_text(item, "cvss3_base_score")
                cvss3_vector_text = _get_child_text(item, "cvss3_vector")
                cvss2_score_text = _get_child_text(item, "cvss_base_score")
                cvss2_vector_text = _get_child_text(item, "cvss_vector")

                # Prefer CVSS3
                if cvss3_score_text:
                    try:
                        cvss_score = float(cvss3_score_text)
                    except ValueError:
                        pass
                    cvss_vector = cvss3_vector_text or None
                elif cvss2_score_text:
                    try:
                        cvss_score = float(cvss2_score_text)
                    except ValueError:
                        pass
                    cvss_vector = cvss2_vector_text or None

                # Build full description
                full_desc = ""
                if synopsis:
                    full_desc += f"**Synopsis**: {synopsis}\n\n"
                if description:
                    full_desc += description

                # References
                refs_parts = []
                if see_also:
                    for ref in see_also.split("\n"):
                        ref = ref.strip()
                        if ref:
                            refs_parts.append(ref)
                # CVE references
                for cve_elem in item.findall("cve"):
                    if cve_elem.text:
                        refs_parts.append(cve_elem.text.strip())

                # Category from plugin family
                category = item.get("pluginFamily", None)

                finding = ParsedFinding(
                    title=plugin_name or f"Nessus Plugin {plugin_id}",
                    severity=severity,
                    description=full_desc or f"Nessus plugin {plugin_id} detected.",
                    impact=synopsis or None,
                    mitigations=solution if solution and solution.lower() != "n/a" else None,
                    references="\n".join(refs_parts) if refs_parts else None,
                    cvss_score=cvss_score,
                    cvss_vector=cvss_vector,
                    category=category,
                    affected_asset_indices=[asset_idx],
                )
                finding_map[plugin_id] = finding

    result.findings = list(finding_map.values())
    result.raw_metadata["total_plugins"] = len(finding_map)
    result.raw_metadata["total_hosts"] = len(result.assets)

    return result
