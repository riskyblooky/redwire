"""rotate_encryption_keys.py covers every encrypted column and never
double-encrypts ciphertext it can't open (a wrong old key)."""

from __future__ import annotations

import sys

import asyncpg
import pytest
from cryptography.fernet import Fernet

import rotate_encryption_keys as rot
from tests.conftest import _test_db_url


# Resolved once: _test_db_url() derives from DATABASE_URL, which _run() repoints.
_TEST_DB_URL = _test_db_url()


def _dsn() -> str:
    return _TEST_DB_URL.replace("postgresql+asyncpg://", "postgresql://", 1)


def test_rotation_map_covers_every_encrypted_column():
    import main  # noqa: F401  (registers every model)
    from database import Base
    from utils.encrypted_types import EncryptedText

    encrypted = {
        (t.name, c.name)
        for t in Base.metadata.sorted_tables for c in t.columns
        if isinstance(c.type, EncryptedText)
    }
    mapped = {(t, c) for t, (_pk, cols) in rot.VAULT_DB_FIELDS.items() for c in cols}
    assert encrypted - mapped == set(), "EncryptedText columns the rotation script would skip"
    for table, (pk, _cols) in {**rot.VAULT_DB_FIELDS, **rot.TOTP_DB_FIELDS}.items():
        assert Base.metadata.tables[table].c[pk].primary_key, f"{table}.{pk} is not the primary key"


def test_rekey_decisions():
    old, new, other = Fernet(Fernet.generate_key()), Fernet(Fernet.generate_key()), Fernet(Fernet.generate_key())
    st = rot.Stats()
    assert rot.rekey_bytes(new.encrypt(b"x"), new, old, st) is None and st.already == 1
    out = rot.rekey_bytes(old.encrypt(b"secret"), new, old, st)
    assert new.decrypt(out) == b"secret" and st.rekeyed == 1
    out = rot.rekey_bytes(b"legacy plaintext", new, old, st)
    assert new.decrypt(out) == b"legacy plaintext" and st.plaintext == 1
    # Ciphertext under a third key: untouched and reported, never wrapped.
    assert rot.rekey_bytes(other.encrypt(b"s"), new, old, st, "t.c id=1") is None
    assert st.undecryptable == ["t.c id=1"] and st.plaintext == 1


@pytest.fixture
async def auth_rows(db_engine):
    conn = await asyncpg.connect(_dsn())
    await conn.execute("DELETE FROM auth_settings WHERE key LIKE 'rot_test_%'")
    yield conn
    await conn.execute("DELETE FROM auth_settings WHERE key LIKE 'rot_test_%'")
    await conn.close()


async def _run(monkeypatch, *args, old, new):
    monkeypatch.setattr(sys, "argv", ["rotate_encryption_keys.py", *args])
    monkeypatch.setenv("DATABASE_URL", _TEST_DB_URL)
    monkeypatch.setenv("OLD_VAULT_ENCRYPTION_KEY", old)
    monkeypatch.setenv("OLD_TOTP_ENCRYPTION_KEY", old)
    monkeypatch.setenv("VAULT_ENCRYPTION_KEY", new)
    monkeypatch.setenv("TOTP_ENCRYPTION_KEY", new)
    await rot.main()


async def test_rotation_rekeys_auth_settings_end_to_end(auth_rows, monkeypatch):
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    await auth_rows.execute("INSERT INTO auth_settings (key, value, is_encrypted) VALUES ('rot_test_ldap', $1, true)",
                            Fernet(old).encrypt(b"bind-pw").decode())
    await _run(monkeypatch, old=old, new=new)
    val = await auth_rows.fetchval("SELECT value FROM auth_settings WHERE key = 'rot_test_ldap'")
    assert Fernet(new).decrypt(val.encode()) == b"bind-pw"


async def test_wrong_old_key_aborts_before_writing(auth_rows, monkeypatch):
    real, wrong, new = (Fernet.generate_key().decode() for _ in range(3))
    good = Fernet(wrong).encrypt(b"rekeyable").decode()      # opens under the supplied old key
    stuck = Fernet(real).encrypt(b"bind-pw").decode()        # opens under neither
    await auth_rows.execute("INSERT INTO auth_settings (key, value, is_encrypted) VALUES ('rot_test_a', $1, true), ('rot_test_b', $2, true)",
                            good, stuck)
    with pytest.raises(SystemExit):
        await _run(monkeypatch, old=wrong, new=new)
    rows = dict(await auth_rows.fetch("SELECT key, value FROM auth_settings WHERE key LIKE 'rot_test_%'"))
    assert rows == {"rot_test_a": good, "rot_test_b": stuck}, "nothing may be written after a failed preflight"

    # Overridden: the rest is re-keyed, the undecryptable value is left as is.
    await _run(monkeypatch, "--allow-undecryptable", old=wrong, new=new)
    rows = dict(await auth_rows.fetch("SELECT key, value FROM auth_settings WHERE key LIKE 'rot_test_%'"))
    assert Fernet(new).decrypt(rows["rot_test_a"].encode()) == b"rekeyable"
    assert rows["rot_test_b"] == stuck and Fernet(real).decrypt(stuck.encode()) == b"bind-pw"
