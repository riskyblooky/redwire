"""
utils/parsers/httpx.py — ProjectDiscovery httpx JSON output parser.

Parses `httpx -json` / `-jsonl` output (one JSON object per probed URL). httpx
is web-service discovery, not vulnerability scanning, so it yields assets and
ports only: one asset per host, one port per probed host:port (service
http/https, version = the Server header), and a description listing each URL
with its status code, title and detected technologies.

Field names changed across httpx releases (``status-code`` → ``status_code``,
``content-length`` → ``content_length``, ``technologies`` → ``tech``); both
spellings are accepted.
"""

import ipaddress
import json
from typing import Optional
from urllib.parse import urlparse

from utils.parsers import ParsedAsset, ParsedImportData, ParsedPort


def _first(item: dict, *keys):
    for k in keys:
        v = item.get(k)
        if v not in (None, "", []):
            return v
    return None


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def _int(v) -> Optional[int]:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def looks_like_httpx(item: dict) -> bool:
    """True for an httpx result object (vs. a Nuclei one)."""
    if any(k in item for k in ("template-id", "templateID", "template")):
        return False
    return "url" in item and any(
        k in item for k in ("status_code", "status-code", "webserver", "tech", "technologies", "title", "content_length", "content-length")
    )


def parse(content: bytes) -> ParsedImportData:
    result = ParsedImportData(source_tool="httpx")
    text = content.decode("utf-8", errors="ignore").strip()
    if not text:
        result.warnings.append("Empty file.")
        return result

    items: list = []
    if text.startswith("["):
        try:
            items = json.loads(text)
        except json.JSONDecodeError as e:
            result.warnings.append(f"JSON parse error: {e}")
            return result
    else:
        for line_num, line in enumerate(text.splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                result.warnings.append(f"Skipped invalid JSON on line {line_num}")

    asset_index: dict[str, int] = {}
    urls_by_asset: dict[int, list[str]] = {}
    probed = 0

    for item in items:
        if not isinstance(item, dict):
            continue
        url = _first(item, "url")
        if not isinstance(url, str):
            continue
        try:
            parsed_url = urlparse(url)
        except ValueError:
            result.warnings.append(f"Skipped unparseable URL: {url[:200]}")
            continue
        scheme = (parsed_url.scheme or _first(item, "scheme") or "http").lower()
        host = parsed_url.hostname or _first(item, "input", "host")
        if not host:
            continue
        port = parsed_url.port or _int(_first(item, "port")) or (443 if scheme == "https" else 80)
        probed += 1

        if host not in asset_index:
            ips = item.get("a") or ([item["host"]] if isinstance(item.get("host"), str) and _is_ip(item["host"]) else [])
            asset_index[host] = len(result.assets)
            result.assets.append(ParsedAsset(
                name=host,
                asset_type="IP Address" if _is_ip(host) else "Domain",
                identifier=host,
                description="",
            ))
            urls_by_asset[asset_index[host]] = []
            if ips and not _is_ip(host):
                urls_by_asset[asset_index[host]].append(f"Resolves to: {', '.join(str(i) for i in ips[:10])}")
        idx = asset_index[host]
        asset = result.assets[idx]

        webserver = _first(item, "webserver")
        if not any(p.port_number == port for p in asset.ports):
            asset.ports.append(ParsedPort(
                port_number=port, protocol="TCP", service_name=scheme, state="OPEN",
                version=str(webserver)[:255] if webserver else None,
            ))

        status = _first(item, "status_code", "status-code")
        title = _first(item, "title")
        tech = _first(item, "tech", "technologies") or []
        if isinstance(tech, str):
            tech = [tech]
        line = f"- `{url}`"
        if status is not None:
            line += f" — {status}"
        if title:
            line += f" — {str(title)[:200]}"
        if tech:
            line += f" ({', '.join(str(t) for t in tech[:15])})"
        urls_by_asset[idx].append(line)

    for idx, lines in urls_by_asset.items():
        result.assets[idx].description = "Imported from httpx\n\n" + "\n".join(lines)

    if not result.assets:
        result.warnings.append("No httpx results found.")
    result.raw_metadata.update({"probed_urls": probed, "total_hosts": len(result.assets)})
    return result
