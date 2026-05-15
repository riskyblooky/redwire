"""
utils/parsers/nmap.py — Nmap XML Output Parser (unified parser wrapper)

Reuses the existing Nmap parsing logic from the asset router but returns
the standardised ParsedImportData format. This parser only produces
assets + ports (no findings, since Nmap is a port scanner, not a vuln
scanner). Extracts OS detection and script output as asset descriptions.
"""

import defusedxml.ElementTree as ET
from utils.parsers import (
    ParsedImportData, ParsedAsset, ParsedPort,
)


def parse(content: bytes) -> ParsedImportData:
    """Parse Nmap XML output into ParsedImportData."""
    result = ParsedImportData(source_tool="nmap")

    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        result.warnings.append(f"XML parse error: {e}")
        return result

    # Metadata
    result.raw_metadata["scanner"] = root.get("scanner", "nmap")
    result.raw_metadata["args"] = root.get("args", "")
    result.raw_metadata["start"] = root.get("startstr", "")

    for host in root.findall(".//host"):
        # Skip hosts that are down
        status_elem = host.find("status")
        if status_elem is not None and status_elem.get("state") != "up":
            continue

        # Get address
        addr_elem = host.find("address")
        if addr_elem is None:
            continue

        addr = addr_elem.get("addr", "")
        addr_type = addr_elem.get("addrtype", "ipv4")
        if not addr:
            continue

        # MAC address (if present)
        mac_addr = None
        for extra_addr in host.findall("address"):
            if extra_addr.get("addrtype") == "mac":
                mac_addr = extra_addr.get("addr")

        # Determine asset type
        asset_type = "IP Address" if addr_type in ("ipv4", "ipv6") else "Other"

        # Try to get hostname
        hostname = None
        hostnames_elem = host.find("hostnames")
        if hostnames_elem is not None:
            hn = hostnames_elem.find("hostname")
            if hn is not None:
                hostname = hn.get("name")

        display_name = hostname or addr

        # OS detection
        os_info = None
        os_elem = host.find("os")
        if os_elem is not None:
            os_match = os_elem.find("osmatch")
            if os_match is not None:
                os_info = f"{os_match.get('name', '')} (accuracy: {os_match.get('accuracy', '?')}%)"

        # Build description
        desc_parts = ["Imported from Nmap scan"]
        if hostname and hostname != addr:
            desc_parts.append(f"Hostname: {hostname}")
        if os_info:
            desc_parts.append(f"OS: {os_info}")
        if mac_addr:
            desc_parts.append(f"MAC: {mac_addr}")

        # Parse ports
        ports = []
        ports_elem = host.find("ports")
        if ports_elem is not None:
            for port_elem in ports_elem.findall("port"):
                port_str = port_elem.get("portid", "0")
                protocol = port_elem.get("protocol", "tcp").upper()

                state_elem = port_elem.find("state")
                state = "OPEN"
                if state_elem is not None:
                    state_val = state_elem.get("state", "open").upper()
                    if state_val in ("OPEN", "CLOSED", "FILTERED"):
                        state = state_val
                    elif "OPEN" in state_val:
                        state = "OPEN"

                service_elem = port_elem.find("service")
                service_name = None
                version = None
                if service_elem is not None:
                    service_name = service_elem.get("name")
                    product = service_elem.get("product", "")
                    svc_version = service_elem.get("version", "")
                    extra_info = service_elem.get("extrainfo", "")
                    version_parts = [p for p in [product, svc_version, extra_info] if p]
                    if version_parts:
                        version = " ".join(version_parts).strip()

                try:
                    port_num = int(port_str)
                    if 1 <= port_num <= 65535:
                        ports.append(ParsedPort(
                            port_number=port_num,
                            protocol="UDP" if protocol == "UDP" else "TCP",
                            service_name=service_name,
                            state=state,
                            version=version,
                        ))
                except (ValueError, TypeError):
                    continue

        asset = ParsedAsset(
            name=display_name,
            asset_type=asset_type,
            identifier=addr,
            description="\n".join(desc_parts),
            ports=ports,
        )
        result.assets.append(asset)

    result.raw_metadata["total_hosts"] = len(result.assets)

    return result
