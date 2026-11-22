"""Which built-in defaults (tags, types, templates, groups, roles) have been
seeded, so startup seeding creates each one at most once.

Seeders used to re-create any default missing at boot, so an admin who
deleted a default tag, type, template, group or role got it back on the
next restart. The ledger records, per kind, the keys already seeded; a key
in it is never created again, which leaves a deletion deleted. A default
added in a later release isn't in the ledger yet and is seeded once.

Stored as one AuthSetting row per kind (key ``seeded_defaults:<kind>``,
JSON list of keys), the same store as the seed_permissions revision
watermark.

The first run on an existing install (no ledger row yet, rows of that kind
already present) records the defaults without creating any: before the
ledger every boot re-created them, so a default missing now was deleted
since the last boot. A fresh install (no rows yet) seeds them all.
"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

_PREFIX = "seeded_defaults:"


class SeedLedger:
    def __init__(self, db: AsyncSession, kind: str, seen: set, bootstrap: bool, row) -> None:
        self._db, self._kind, self._seen, self._bootstrap, self._row = db, kind, seen, bootstrap, row

    @classmethod
    async def open(cls, db: AsyncSession, kind: str, model) -> "SeedLedger":
        """``model``: the table the defaults live in (decides fresh vs existing install)."""
        from models.auth_settings import AuthSetting
        row = await db.get(AuthSetting, _PREFIX + kind)
        if row is not None:
            try:
                seen = set(json.loads(row.value or "[]"))
            except ValueError:
                seen = set()
            return cls(db, kind, seen, False, row)
        has_rows = (await db.execute(select(model).limit(1))).first() is not None
        return cls(db, kind, set(), has_rows, None)

    def should_create(self, key: str) -> bool:
        return not self._bootstrap and key not in self._seen

    def mark(self, key: str) -> None:
        self._seen.add(key)

    async def save(self) -> None:
        from models.auth_settings import AuthSetting
        value = json.dumps(sorted(self._seen))
        if self._row is None:
            self._row = AuthSetting(key=_PREFIX + self._kind, value=value, is_encrypted=False)
            self._db.add(self._row)
        else:
            self._row.value = value
