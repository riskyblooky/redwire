"""
http_log_ingest.py — feed nginx's JSON access log into the Security Center.

nginx writes one JSON object per request to a shared volume
(``log_format security_json`` in nginx/nginx.conf). Every few seconds one
worker reads the new bytes from its saved offset, flags scanner probes and
tool user agents, inserts ``http_requests`` rows and bumps the hourly
rollups. A Postgres transaction-scoped advisory lock makes the pass
exclusive across workers (no reliance on Redis), and the offset is
committed in the same transaction as the rows, so a crash never double-
counts.

The file is capped by copy-truncate: once the ingester has caught up and
the file is over ``MAX_BYTES``, it truncates it in place. nginx opens access
logs O_APPEND, so it simply carries on writing at the new end. Lines
written in the moment between the final read and the truncate are lost —
an accepted gap for a monitoring feed.
"""

import json
import logging
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, text, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert

logger = logging.getLogger(__name__)

LOG_PATH = os.getenv("NGINX_SECURITY_LOG", "/var/log/redwire-nginx/access.json")
MAX_BYTES = int(os.getenv("NGINX_SECURITY_LOG_MAX_BYTES", str(50 * 1024 * 1024)))
READ_CHUNK = 4 * 1024 * 1024  # bytes per pass
INTERVAL = 10  # seconds between passes
_LOCK_KEY = 0x5277_4C67  # "RwLg"
_CURSOR = "nginx"

# Paths that don't exist in RedWire and are only ever requested by scanners
# and bots looking for other software (or secrets left in a web root).
_PROBE = re.compile(
    r"(^/(wp-|wordpress|xmlrpc\.php|phpmyadmin|pma/|myadmin|cgi-bin|vendor/phpunit|actuator"
    r"|server-status|boaform|hnap1|solr|jenkins|manager/html|owa/|autodiscover|_ignition"
    r"|telescope|druid|console(/|$)|remote/login|geoserver|\.well-known/(?!acme-challenge))"
    r"|/\.(env|git|svn|hg|aws|ssh|docker|htaccess|htpasswd|ds_store|vscode|idea)"
    r"|\.(php\d?|asp|aspx|jsp|cgi|pl|sql|bak|old|swp)$"
    r"|\.\./|/etc/passwd|win\.ini)",
    re.IGNORECASE,
)
_SCANNER_UA = re.compile(
    r"sqlmap|nikto|nuclei|zgrab|masscan|nmap|gobuster|dirbuster|dirb/|ffuf|wfuzz|feroxbuster"
    r"|wpscan|acunetix|nessus|openvas|qualys|netsparker|arachni|whatweb|httpx|censys"
    r"|shodan|expanse|internet-measurement|l9explore|leakix|odin\.io",
    re.IGNORECASE,
)
_TOOL_UA = re.compile(r"python-requests|python-urllib|aiohttp|go-http-client|curl/|wget/|libwww|okhttp|java/|httpie", re.IGNORECASE)


def classify(path: str, ua: str) -> list[str]:
    flags = []
    if path and _PROBE.search(path):
        flags.append("probe")
    if ua and _SCANNER_UA.search(ua):
        flags.append("scanner_ua")
    elif ua and _TOOL_UA.search(ua):
        flags.append("tool_ua")
    return flags


def _area(path: str) -> str:
    if path.startswith("/api/ws") or path.startswith("/ws"):
        return "ws"
    if path.startswith("/api/"):
        return "api"
    return "web"


def _ts(raw: str) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def parse_line(line: str) -> Optional[dict]:
    try:
        d = json.loads(line)
        status = int(d.get("status"))
    except (ValueError, TypeError, AttributeError):
        return None
    ts = _ts(d.get("ts"))
    if ts is None:
        return None
    path = str(d.get("path") or "")[:1000]
    ua = str(d.get("ua") or "")[:500]
    try:
        duration = int(float(d.get("rt") or 0) * 1000)
    except (TypeError, ValueError):
        duration = None
    try:
        size = int(d.get("bytes") or 0)
    except (TypeError, ValueError):
        size = None
    return {
        "ts": ts,
        "ip": (str(d.get("ip") or "")[:64]) or None,
        "method": (str(d.get("method") or "")[:16]) or None,
        "path": path,
        "status": status,
        "bytes": size,
        "duration_ms": duration,
        "host": (str(d.get("host") or "")[:255]) or None,
        "user_agent": ua or None,
        "referer": (str(d.get("ref") or "")[:500]) or None,
        "area": _area(path),
        "flags": ",".join(classify(path, ua)) or None,
    }


def _rollup(rows: list[dict]) -> list[dict]:
    buckets: dict = defaultdict(lambda: defaultdict(int))
    for r in rows:
        b = buckets[r["ts"].replace(minute=0, second=0, microsecond=0)]
        b["requests"] += 1
        s = r["status"]
        if 200 <= s < 300:
            b["s2xx"] += 1
        elif 300 <= s < 400:
            b["s3xx"] += 1
        elif 400 <= s < 500:
            b["s4xx"] += 1
        elif s >= 500:
            b["s5xx"] += 1
        if s == 429:
            b["s429"] += 1
        flags = r["flags"] or ""
        if "probe" in flags:
            b["probes"] += 1
        if "scanner_ua" in flags:
            b["scanner"] += 1
    return [{"bucket": k, **v} for k, v in buckets.items()]


async def ingest_once(session_factory=None, path: str = LOG_PATH) -> int:
    """One ingest pass; returns the number of lines stored. No-op when the log
    file isn't there (dev without the volume, tests) or another worker holds
    the lock."""
    if not os.path.exists(path):
        return 0
    from models.security_event import HttpRequestLog, HttpTrafficHourly, HttpLogCursor
    if session_factory is None:
        import database
        session_factory = database.AsyncSessionLocal

    async with session_factory() as db:
        if not (await db.execute(text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": _LOCK_KEY})).scalar():
            return 0
        cursor = await db.get(HttpLogCursor, _CURSOR)
        if cursor is None:
            cursor = HttpLogCursor(name=_CURSOR, offset=0)
            db.add(cursor)
        st = os.stat(path)
        if cursor.inode != st.st_ino or st.st_size < (cursor.offset or 0):
            cursor.inode, cursor.offset = st.st_ino, 0  # new or truncated file

        with open(path, "rb") as f:
            f.seek(cursor.offset)
            chunk = f.read(READ_CHUNK)
        end = chunk.rfind(b"\n")
        if end < 0:
            consumed, lines = 0, []
        else:
            consumed = end + 1
            lines = chunk[:consumed].decode("utf-8", "replace").splitlines()

        rows = [r for r in (parse_line(l) for l in lines if l.strip()) if r]
        if rows:
            await db.execute(pg_insert(HttpRequestLog), rows)
            for agg in _rollup(rows):
                stmt = pg_insert(HttpTrafficHourly).values(**agg)
                cols = {c: getattr(HttpTrafficHourly, c) + getattr(stmt.excluded, c)
                        for c in agg if c != "bucket"}
                await db.execute(stmt.on_conflict_do_update(index_elements=["bucket"], set_=cols))
        cursor.offset = (cursor.offset or 0) + consumed
        cursor.updated_at = datetime.utcnow()

        # Caught up and over the cap → copy-truncate (see module docstring).
        if cursor.offset >= MAX_BYTES and os.stat(path).st_size == cursor.offset:
            try:
                os.truncate(path, 0)
                cursor.offset = 0
            except OSError as e:
                logger.warning("security log truncate failed: %s", e)
        await db.commit()
        return len(rows)


async def status(db) -> dict:
    """Ingest health for the Posture tab."""
    from models.security_event import HttpLogCursor
    cursor = await db.get(HttpLogCursor, _CURSOR)
    present = os.path.exists(LOG_PATH)
    return {
        "configured": present,
        "path": LOG_PATH,
        "last_ingest": cursor.updated_at.isoformat() + "Z" if cursor and cursor.updated_at else None,
        "pending_bytes": max(0, os.stat(LOG_PATH).st_size - (cursor.offset if cursor else 0)) if present else None,
    }


# ── Retention ───────────────────────────────────────────────────────────────

DEFAULT_RETENTION = {"http_days": 14, "events_days": 365, "rollup_days": 365}
_RETENTION_KEYS = {k: f"security_retention_{k}" for k in DEFAULT_RETENTION}


async def get_retention(db) -> dict:
    from models.auth_settings import AuthSetting
    rows = (await db.execute(select(AuthSetting).where(AuthSetting.key.in_(_RETENTION_KEYS.values())))).scalars().all()
    stored = {r.key: r.value for r in rows}
    out = {}
    for k, default in DEFAULT_RETENTION.items():
        try:
            out[k] = int(stored.get(_RETENTION_KEYS[k]) or default)
        except ValueError:
            out[k] = default
    return out


async def set_retention(db, values: dict, user_id: str) -> dict:
    from models.auth_settings import AuthSetting
    for k, v in values.items():
        key = _RETENTION_KEYS[k]
        row = await db.get(AuthSetting, key)
        if row is None:
            db.add(AuthSetting(key=key, value=str(int(v)), updated_by=user_id))
        else:
            row.value, row.updated_by = str(int(v)), user_id
    await db.commit()
    return await get_retention(db)


async def prune(session_factory=None) -> dict:
    from models.security_event import SecurityEvent, HttpRequestLog, HttpTrafficHourly
    if session_factory is None:
        import database
        session_factory = database.AsyncSessionLocal
    async with session_factory() as db:
        r = await get_retention(db)
        now = datetime.utcnow()
        out = {}
        for name, model, col, days in (
            ("http_requests", HttpRequestLog, HttpRequestLog.ts, r["http_days"]),
            ("security_events", SecurityEvent, SecurityEvent.created_at, r["events_days"]),
            ("http_traffic_hourly", HttpTrafficHourly, HttpTrafficHourly.bucket, r["rollup_days"]),
        ):
            res = await db.execute(delete(model).where(col < now - timedelta(days=days)))
            out[name] = res.rowcount or 0
        await db.commit()
        return out


async def run_forever() -> None:
    """Lifespan task: ingest every INTERVAL seconds; prune hourly (one
    worker, via the cluster claim)."""
    import asyncio
    from utils.cluster import claim

    await asyncio.sleep(5)
    last_prune = 0.0
    loop = asyncio.get_running_loop()
    while True:
        try:
            # Drain a backlog in consecutive passes before sleeping.
            while await ingest_once() > 0 and os.path.exists(LOG_PATH):
                pass
            if loop.time() - last_prune > 3600:
                last_prune = loop.time()
                if await claim("security_prune", 3500):
                    removed = await prune()
                    if any(removed.values()):
                        logger.info("security retention prune: %s", removed)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("security log ingest error: %s", e)
        await asyncio.sleep(INTERVAL)
