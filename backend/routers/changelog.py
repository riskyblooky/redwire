"""routers/changelog.py — in-app release notes.

Parses backend/CHANGELOG.md into per-release entries and tracks, per user, the
highest release whose notes they've seen (User.last_seen_version) so the
frontend can show a one-time "What's New" modal accumulating everything since.
"""

import re
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.user import User
from auth.dependencies import get_current_user
from version import VERSION, _to_tuple

router = APIRouter(prefix="/changelog", tags=["changelog"])

CHANGELOG_PATH = Path(__file__).resolve().parent.parent / "CHANGELOG.md"

# "## [1.1.0] — 2026-08-12"  (accepts -, – or — as the separator)
_HEADING_RE = re.compile(r"^##\s*\[([^\]]+)\]\s*[-–—]\s*(.+?)\s*$")


def _parse_changelog() -> list[dict]:
    """Parse CHANGELOG.md into [{version, date, body}] in file order (newest
    first, as authored). Body is the markdown between this heading and the next."""
    try:
        text = CHANGELOG_PATH.read_text(encoding="utf-8")
    except OSError:
        return []

    entries: list[dict] = []
    current: dict | None = None
    for line in text.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            if current is not None:
                current["body"] = current["body"].strip()
                entries.append(current)
            current = {"version": m.group(1).strip(), "date": m.group(2).strip(), "body": ""}
        elif current is not None:
            current["body"] += line + "\n"
    if current is not None:
        current["body"] = current["body"].strip()
        entries.append(current)
    return entries


def _newer(a: str, b: str) -> bool:
    return _to_tuple(a) > _to_tuple(b)


@router.get("")
async def get_changelog(current_user: User = Depends(get_current_user)):
    """Full release history."""
    return {"current_version": VERSION, "entries": _parse_changelog()}


@router.get("/unseen")
async def get_unseen_changelog(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Releases newer than what this user last saw. A null last_seen (brand-new
    user, or first rollout of this feature) is silently marked seen so nobody
    gets a dump of historical notes."""
    user = (await db.execute(select(User).where(User.id == current_user.id))).scalar_one()

    if user.last_seen_version is None:
        user.last_seen_version = VERSION
        await db.commit()
        return {"has_unseen": False, "current_version": VERSION, "entries": []}

    entries = [e for e in _parse_changelog() if _newer(e["version"], user.last_seen_version)]
    return {"has_unseen": bool(entries), "current_version": VERSION, "entries": entries}


@router.post("/seen")
async def mark_changelog_seen(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark the current release's notes as seen for this user."""
    user = (await db.execute(select(User).where(User.id == current_user.id))).scalar_one()
    user.last_seen_version = VERSION
    await db.commit()
    return {"ok": True, "last_seen_version": VERSION}
