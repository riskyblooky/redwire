"""In-app help / documentation.

Serves the Markdown guides that ship in ``backend/help/`` so the frontend can
render them with the existing Markdown pipeline (sanitizer + highlighting) at
``/help``. Content is read from disk at request time, so updating a guide is
just editing the ``.md`` file — no rebuild of the app tree needed beyond the
usual image rebuild.

Access: every authenticated user can read the user guide; the admin/plugin
guides are gated to ADMIN / READ_ONLY_ADMIN (system administrators), not
engagement managers.
"""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status

from auth.dependencies import get_current_user
from models.user import User, UserRole

router = APIRouter(prefix="/help", tags=["help"])

HELP_DIR = Path(__file__).resolve().parent.parent / "help"

# Registry of shipped guides. `admin_only` gates on system-admin roles.
_DOCS = [
    {
        "slug": "user",
        "title": "User Guide",
        "description": "Running an engagement end to end — findings, evidence, reports, chat.",
        "file": "user.md",
        "admin_only": False,
    },
    {
        "slug": "admin",
        "title": "Admin Guide",
        "description": "Install, TLS, backups, upgrades, credential rotation, integrations.",
        "file": "admin.md",
        "admin_only": True,
    },
    {
        "slug": "plugins",
        "title": "Plugin Guide",
        "description": "Writing, installing, and configuring RedWire plugins.",
        "file": "plugins.md",
        "admin_only": True,
    },
]
_BY_SLUG = {d["slug"]: d for d in _DOCS}

_ADMIN_ROLES = (UserRole.ADMIN, UserRole.READ_ONLY_ADMIN)


def _is_admin(user: User) -> bool:
    return user.role in _ADMIN_ROLES


@router.get("/docs")
async def list_help_docs(current_user: User = Depends(get_current_user)):
    """List the guides the caller may read (admin guides hidden from non-admins)."""
    admin = _is_admin(current_user)
    return [
        {
            "slug": d["slug"],
            "title": d["title"],
            "description": d["description"],
            "admin_only": d["admin_only"],
        }
        for d in _DOCS
        if admin or not d["admin_only"]
    ]


@router.get("/docs/{slug}")
async def get_help_doc(slug: str, current_user: User = Depends(get_current_user)):
    """Return one guide's Markdown content, enforcing the admin gate."""
    doc = _BY_SLUG.get(slug)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Help document not found")
    if doc["admin_only"] and not _is_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This guide is available to administrators only.",
        )
    path = HELP_DIR / doc["file"]
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Help content is missing.")
    return {"slug": slug, "title": doc["title"], "content": path.read_text(encoding="utf-8")}
