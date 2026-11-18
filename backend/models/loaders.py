"""What each response loads, in one place.

Core relationships are ``lazy="raise"``: touching one that wasn't loaded is
an error instead of a silent query. They used to be ``lazy="selectin"``,
which chained: a finding loaded its assets, each asset its ports, findings,
test cases, vault items (decrypting them) and cleanup items, and those their
own links in turn. The response models only show links one level deep
(``LinkedAssetResponse`` and friends are plain columns), so each option set
here loads exactly that level.

Use with ``select(Model).options(*options("FINDING"))``, or ``load(db, Model, id)`` to
(re)read one row ready for its response (after a create or update, instead
of ``db.refresh``, which doesn't load relationships).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import configure_mappers, selectinload

from models.asset import Asset
from models.cleanup_artifact import CleanupArtifact
from models.finding import Finding
from models.infra_item import InfraItem
from models.intel_item import IntelItem
from models.note import Note
from models.testcase import TestCase
from models.vault import VaultItem


def _build() -> dict:
    configure_mappers()  # backrefs (Asset.testcases, ...) exist only after this
    return {
        "FINDING": (
            selectinload(Finding.assets),
            selectinload(Finding.tags),
            selectinload(Finding.testcases),
            selectinload(Finding.vault_items),
            selectinload(Finding.cleanup_artifacts),
            selectinload(Finding.attack_techniques),
        ),
        "ASSET": (
            selectinload(Asset.ports),
            selectinload(Asset.findings),
            selectinload(Asset.testcases),
            selectinload(Asset.vault_items),
            selectinload(Asset.cleanup_artifacts),
        ),
        "TESTCASE": (
            selectinload(TestCase.assets),
            selectinload(TestCase.tags),
            selectinload(TestCase.findings),
            selectinload(TestCase.vault_items),
            selectinload(TestCase.cleanup_artifacts),
            selectinload(TestCase.evidence),
            selectinload(TestCase.attack_techniques),
        ),
        "VAULT_ITEM": (
            selectinload(VaultItem.findings),
            selectinload(VaultItem.testcases),
            selectinload(VaultItem.assets),
        ),
        "CLEANUP_ARTIFACT": (
            selectinload(CleanupArtifact.findings),
            selectinload(CleanupArtifact.testcases),
            selectinload(CleanupArtifact.assets),
        ),
        "NOTE": (
            selectinload(Note.findings),
            selectinload(Note.testcases),
            selectinload(Note.assets),
            selectinload(Note.vault_items),
            selectinload(Note.cleanup_artifacts),
        ),
        "INTEL_ITEM": (
            selectinload(IntelItem.findings),
            selectinload(IntelItem.testcases),
            selectinload(IntelItem.notes),
            selectinload(IntelItem.attachments),
        ),
        "INFRA_ITEM": (
            selectinload(InfraItem.findings),
            selectinload(InfraItem.testcases),
            selectinload(InfraItem.notes_rel),
        ),
    }


_BUILT: dict | None = None


def options(name: str) -> tuple:
    """Loader options for a response, e.g. ``options("FINDING")``."""
    global _BUILT
    if _BUILT is None:
        _BUILT = _build()
    return _BUILT[name]


_FOR_MODEL = {
    Finding: "FINDING",
    Asset: "ASSET",
    TestCase: "TESTCASE",
    VaultItem: "VAULT_ITEM",
    CleanupArtifact: "CLEANUP_ARTIFACT",
    Note: "NOTE",
    IntelItem: "INTEL_ITEM",
    InfraItem: "INFRA_ITEM",
}


async def load(db, model, obj_id, *extra):
    """One row with its response's relationships, re-read from the DB
    (``populate_existing``, so it also replaces a stale copy in the session).
    Returns None if it doesn't exist."""
    stmt = (select(model).where(model.id == obj_id)
            .options(*(options(_FOR_MODEL[model]) if model in _FOR_MODEL else ()), *extra)
            .execution_options(populate_existing=True))
    return (await db.execute(stmt)).scalar_one_or_none()
