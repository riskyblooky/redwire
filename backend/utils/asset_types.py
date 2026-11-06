"""
asset_types.py — map asset type strings onto the configured asset types.

Asset types are admin-configurable (``configurable_types`` rows with
category "asset", e.g. "IP Address", "Domain"). Older clients, imports and
the MCP server have sent other spellings (``IP_ADDRESS``, ``host``,
``web_application``), which the edit form can't show — its Type dropdown
renders blank. Every write path canonicalizes through here so the stored
value is always a configured name.
"""

from typing import Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Legacy / tool spellings → default type name. Keys are _key()-normalized.
ALIASES = {
    "IP_ADDRESS": "IP Address", "IP": "IP Address", "IPADDRESS": "IP Address",
    "IPV4": "IP Address", "IPV6": "IP Address",
    "DOMAIN": "Domain", "DNS": "Domain", "HOSTNAME": "Domain", "FQDN": "Domain",
    "URL": "URL", "URI": "URL",
    "APPLICATION": "Application", "APP": "Application", "WEB_APPLICATION": "Application",
    "WEB_APP": "Application", "WEBAPP": "Application", "API": "Application",
    "SERVER": "Server", "HOST": "Server", "WORKSTATION": "Server",
    "NETWORK": "Network", "SUBNET": "Network", "CIDR": "Network", "NETWORK_DEVICE": "Network",
    "OTHER": "Other",
}


def _key(value: str) -> str:
    return "_".join(value.strip().upper().replace("-", " ").replace("_", " ").split())


def canonical_name(raw: Optional[str], configured: Iterable[str]) -> Optional[str]:
    """The configured type ``raw`` refers to, or None if it matches none.

    A configured name matches case- and separator-insensitively ("ip address",
    "IP_ADDRESS"); otherwise a known alias maps to its default type, provided
    that type is still configured.
    """
    if not raw or not raw.strip():
        return None
    by_key = {_key(n): n for n in configured}
    k = _key(raw)
    if k in by_key:
        return by_key[k]
    alias = ALIASES.get(k)
    if alias is not None:
        return by_key.get(_key(alias))
    return None


async def configured_asset_types(db: AsyncSession) -> List[str]:
    from models.configurable_type import ConfigurableType
    rows = await db.execute(
        select(ConfigurableType.name)
        .where(ConfigurableType.category == "asset")
        .order_by(ConfigurableType.sort_order)
    )
    return list(rows.scalars().all())


async def resolve_asset_type(raw: Optional[str], db: AsyncSession, fallback: Optional[str] = None) -> Optional[str]:
    """Canonical configured name for ``raw``; ``fallback`` (also canonicalized)
    when it matches nothing. None if neither resolves."""
    configured = await configured_asset_types(db)
    if not configured:  # nothing configured to map onto — keep what was sent
        return (raw or "").strip() or fallback
    return canonical_name(raw, configured) or (canonical_name(fallback, configured) if fallback else None)
