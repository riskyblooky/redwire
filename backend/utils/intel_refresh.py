"""Fetch enabled intel feeds and store new items.

One implementation for the manual "Refresh feeds" endpoint and the
background refresher (they used to be two copies of the same loop).

Items dedupe on (feed_id, source_url) through the ``uq_intel_items_feed_source_url``
index with ``ON CONFLICT DO NOTHING``, so two refreshes running at once (two
workers, or a manual refresh during the background one) can't insert the
same item twice. Each feed is stored in its own savepoint: a bad row from
one feed can't abort the others.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime

import defusedxml.ElementTree as ET
import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from models.intel_feed import IntelFeed
from models.intel_item import IntelItem
from utils.ssrf import OutboundURLError, validate_outbound_url

logger = logging.getLogger(__name__)

_ATOM = "{http://www.w3.org/2005/Atom}"
_CVE_RE = re.compile(r"CVE-\d{4}-\d+")
MAX_ENTRIES_PER_FEED = 30


def _get_text(element, tag):
    el = element.find(tag)
    if el is not None and el.text:
        return el.text.strip()
    return None


def _strip_html(text):
    return re.sub(r"<[^>]+>", "", text)


def _parse_date(date_str):
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def _parse_rss_date(date_str):
    if not date_str:
        return None
    from email.utils import parsedate_to_datetime
    try:
        return parsedate_to_datetime(date_str).replace(tzinfo=None)
    except Exception:
        return _parse_date(date_str)


def _synthetic_key(*parts) -> str:
    import hashlib
    digest = hashlib.sha256("\x1f".join(str(p or "") for p in parts).encode()).hexdigest()[:32]
    return f"urn:redwire:intel:{digest}"


def parse_entries(feed_type: str, resp: httpx.Response) -> list[dict]:
    """Turn a feed response into item dicts. Raises on unparseable XML/JSON."""
    entries = []
    if feed_type == "JSON":
        data = resp.json()
        # A top-level list (not the CISA KEV {"vulnerabilities": [...]} shape)
        # used to fail every refresh: .get on a list.
        vulns = data if isinstance(data, list) else (data.get("vulnerabilities") or [] if isinstance(data, dict) else [])
        for v in vulns[:MAX_ENTRIES_PER_FEED]:
            if not isinstance(v, dict):
                continue
            cve = v.get("cveID")
            entries.append({
                "title": v.get("vulnerabilityName") or cve or "Unknown",
                "content": v.get("shortDescription", ""),
                # No CVE id: no shared ".../detail/" URL that would collapse
                # every such entry into one item; keyed by content instead.
                "source_url": f"https://nvd.nist.gov/vuln/detail/{cve}" if cve else _synthetic_key(v.get("vulnerabilityName"), v.get("dateAdded")),
                "cve_id": v.get("cveID"),
                "item_type": "CVE",
                "severity": "HIGH" if v.get("knownRansomwareCampaignUse") == "Known" else None,
                "published_at": _parse_date(v.get("dateAdded")),
            })
        return entries

    root = ET.fromstring(resp.text)
    items_el = root.findall(".//item") or root.findall(f".//{_ATOM}entry")
    for el in items_el[:MAX_ENTRIES_PER_FEED]:
        title = _get_text(el, "title") or _get_text(el, f"{_ATOM}title") or "Untitled"
        link = _get_text(el, "link") or ""
        if not link:
            link_el = el.find(f"{_ATOM}link")
            if link_el is not None:
                link = link_el.get("href", "")
        desc = _get_text(el, "description") or _get_text(el, f"{_ATOM}summary") or ""
        pub_date = _get_text(el, "pubDate") or _get_text(el, f"{_ATOM}updated") or ""
        if not link:
            # No link: dedupe on the entry's guid / id, else a stable hash.
            # A linkless entry had no conflict key and was re-inserted on
            # every refresh.
            link = (_get_text(el, "guid") or _get_text(el, f"{_ATOM}id")
                    or _synthetic_key(title, pub_date))
        m = _CVE_RE.search(title)
        cve_id = m.group(0) if m else None
        item_type = "CVE" if cve_id else "ARTICLE"
        lowered = title.lower()
        if any(kw in lowered for kw in ("advisory", "alert", "bulletin")):
            item_type = "ADVISORY"
        elif any(kw in lowered for kw in ("exploit", "poc", "proof of concept")):
            item_type = "EXPLOIT"
        entries.append({
            "title": title,
            "content": _strip_html(desc)[:2000] if desc else None,
            "source_url": link,
            "cve_id": cve_id,
            "item_type": item_type,
            "published_at": _parse_rss_date(pub_date),
        })
    return entries


def _row(feed: IntelFeed, entry: dict) -> dict:
    """Column values for one entry, clipped to the column sizes so one
    over-long field can't fail the insert."""
    now = datetime.utcnow()
    clip = lambda v, n: v[:n] if isinstance(v, str) else v  # noqa: E731
    return {
        "id": str(uuid.uuid4()),
        "title": clip(entry.get("title") or "Untitled", 500),
        "content": entry.get("content"),
        "source": clip(feed.name, 255),
        "source_url": entry.get("source_url") or None,
        "item_type": clip(entry.get("item_type") or "OTHER", 20),
        "severity": clip(entry.get("severity"), 20),
        "cve_id": clip(entry.get("cve_id"), 50),
        "published_at": entry.get("published_at"),
        "feed_id": feed.id,
        "created_at": now,
        "updated_at": now,
    }


async def store_entries(db, feed: IntelFeed, entries: list[dict]) -> int:
    """Insert entries not already stored for this feed; returns how many were new."""
    new = 0
    for entry in entries:
        stmt = pg_insert(IntelItem).values(**_row(feed, entry))
        if entry.get("source_url"):
            stmt = stmt.on_conflict_do_nothing(
                index_elements=["feed_id", "source_url"],
                index_where=IntelItem.feed_id.isnot(None) & IntelItem.source_url.isnot(None),
            )
        result = await db.execute(stmt)
        new += result.rowcount or 0
    return new


async def _fetch(client: httpx.AsyncClient, feed: IntelFeed) -> httpx.Response:
    headers = {"User-Agent": "RedWire/1.0"}
    if getattr(feed, "verify_tls", True):
        return await client.get(feed.url, headers=headers)
    logger.warning("TLS verification DISABLED for intel feed %r (%s)", feed.name, feed.url)
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=False, verify=False) as insecure:
        return await insecure.get(feed.url, headers=headers)


async def refresh_enabled_feeds(db) -> tuple[int, int]:
    """Fetch every enabled feed and store new items. Commits.
    Returns (new items, feeds processed)."""
    feeds = (await db.execute(select(IntelFeed).where(IntelFeed.enabled == True))).scalars().all()  # noqa: E712
    total_new = 0
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
        for feed in feeds:
            name = feed.name
            try:
                # SSRF guard (GHSA-f33c-g6w5-6xm6): validate at fetch time;
                # redirects are disabled on the clients.
                try:
                    await validate_outbound_url(feed.url)
                except OutboundURLError as exc:
                    logger.warning("Skipping intel feed %r: %s", feed.url, exc)
                    continue
                resp = await _fetch(client, feed)
                if resp.status_code != 200:
                    continue
                try:
                    entries = parse_entries(feed.feed_type, resp)
                except (ET.ParseError, ValueError):
                    logger.warning("Intel feed %r returned an unparseable body", name)
                    continue
                async with db.begin_nested():
                    total_new += await store_entries(db, feed, entries)
                    feed.last_fetched_at = datetime.utcnow()
            except Exception as exc:  # one feed's failure must not stop the rest
                logger.warning("Error refreshing intel feed %r: %s", name, exc)
                continue
    await db.commit()
    return total_new, len(feeds)
