"""Wordlist API: any authenticated operator can look a hash up (NTLM, MD5,
SHA-1, LM:NT pairs and pwdump lines), salted formats get an explanatory
miss rather than a lookup, and managing the shared dataset (upload /
delete) is refused to operators. Entries are seeded directly: upload
processing runs in a background thread on its own sync engine, outside the
test transaction (and the bloom rebuild on delete is stubbed for the same
reason)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from utils.hash_utils import compute_md5, compute_ntlm, compute_sha1

PLAIN = "Winter2026!" + uuid.uuid4().hex[:6]


@pytest.fixture
async def wordlist(db_session):
    from models.wordlist import WordlistEntry, WordlistMeta
    meta = WordlistMeta(id=str(uuid.uuid4()), filename="rockyou-slice.txt", status="READY", entry_count=1)
    db_session.add(meta)
    await db_session.flush()
    db_session.add(WordlistEntry(password=PLAIN, ntlm=compute_ntlm(PLAIN), md5=compute_md5(PLAIN),
                                 sha1=compute_sha1(PLAIN), source=meta.id))
    await db_session.commit()
    return meta


@pytest.mark.parametrize("make,expected_type", [
    (lambda p: compute_ntlm(p).upper(), "ntlm"),
    (lambda p: compute_md5(p), "md5"),
    (lambda p: compute_sha1(p), "sha1"),
    (lambda p: "aad3b435b51404eeaad3b435b51404ee:" + compute_ntlm(p), "ntlm"),
    (lambda p: f"Administrator:500:aad3b435b51404eeaad3b435b51404ee:{compute_ntlm(p)}:::", "ntlm"),
])
async def test_lookup_finds_each_format(client, make_user, authenticate_as, wordlist, make, expected_type):
    authenticate_as(await make_user())
    body = (await client.post("/wordlist/lookup-hash", json={"hash": make(PLAIN)})).json()
    assert body == {"found": True, "password": PLAIN, "hash_type": expected_type, "note": None}


@pytest.mark.parametrize("h,note", [
    ("$2b$12$" + "a" * 53, "salted"),
    ("$krb5tgs$23$*svc$CORP$http/web*$" + "ab" * 40, "salted"),
    ("not-a-hash", "Unrecognized"),
    ("f" * 32, None),  # well-formed, not in any list
])
async def test_lookup_misses(client, make_user, authenticate_as, wordlist, h, note):
    authenticate_as(await make_user())
    body = (await client.post("/wordlist/lookup-hash", json={"hash": h})).json()
    assert body["found"] is False and body["password"] is None
    assert (note in (body["note"] or "")) if note else body["note"] is None


async def test_lookup_needs_auth_and_bounds_input(client, make_user, authenticate_as):
    assert (await client.post("/wordlist/lookup-hash", json={"hash": "f" * 32})).status_code == 401
    authenticate_as(await make_user())
    assert (await client.post("/wordlist/lookup-hash", json={"hash": "f" * 5000})).status_code == 422
    assert (await client.post("/wordlist/check-password", json={"password": "x" * 300})).status_code == 422


async def test_operators_cannot_manage_the_dataset(client, db_session, make_user, authenticate_as, wordlist, monkeypatch):
    from models.wordlist import WordlistEntry, WordlistMeta
    import routers.wordlist as wl
    monkeypatch.setattr(wl, "_rebuild_bloom_sync", lambda: None)

    authenticate_as(await make_user())
    files = {"file": ("x.txt", b"password1\n", "text/plain")}
    assert (await client.post("/wordlist/upload", files=files)).status_code == 403
    assert (await client.delete(f"/wordlist/{wordlist.id}")).status_code == 403
    db_session.expunge_all()
    assert (await db_session.execute(select(WordlistMeta).where(WordlistMeta.id == wordlist.id))).first()

    # Team leads and read-only admins no longer manage the dataset; a group
    # grant of wordlist_manage does.
    for role in ("team_lead", "read_only_admin"):
        authenticate_as(await make_user(role=role))
        assert (await client.post("/wordlist/upload", files=files)).status_code == 403, role
        assert (await client.delete(f"/wordlist/{wordlist.id}")).status_code == 403, role
    from tests.test_security_center import _grant
    granted = await make_user()
    await _grant(db_session, granted, "wordlist_manage")
    await db_session.commit()
    authenticate_as(granted)
    assert (await client.delete(f"/wordlist/{uuid.uuid4()}")).status_code == 404, "granted: passes the gate"

    authenticate_as(await make_user(role="admin"))
    assert (await client.delete(f"/wordlist/{uuid.uuid4()}")).status_code == 404
    assert (await client.delete(f"/wordlist/{wordlist.id}")).status_code == 200
    db_session.expunge_all()
    left = (await db_session.execute(select(WordlistEntry).where(WordlistEntry.source == wordlist.id))).first()
    assert left is None, "the list's entries outlived it"
