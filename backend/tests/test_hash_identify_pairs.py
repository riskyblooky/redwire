"""LM:NT pairs and pwdump / secretsdump lines are recognised as NTLM and
looked up by their NT field."""

from __future__ import annotations

from utils.hash_utils import compute_ntlm, identify_hash_type, parse_hash

NT = compute_ntlm("Summer2026!")
LM_EMPTY = "aad3b435b51404eeaad3b435b51404ee"


def test_pairs_and_pwdump_lines():
    assert parse_hash(f"{LM_EMPTY}:{NT.upper()}") == ("ntlm", NT)
    assert parse_hash(f"Administrator:500:{LM_EMPTY}:{NT}:::") == ("ntlm", NT)
    assert parse_hash(f"CORP\\svc_sql:1104:{LM_EMPTY}:{NT}:::\n") == ("ntlm", NT)
    # Unchanged shapes
    assert parse_hash(NT.upper()) == ("md5_or_ntlm", NT)
    assert identify_hash_type("a" * 40) == "sha1"
    assert identify_hash_type("$2b$12$abc") == "bcrypt"
    assert identify_hash_type(f"user:notarid:{LM_EMPTY}:{NT}") is None
    assert identify_hash_type(f"{LM_EMPTY}:zz") is None


async def test_lookup_finds_the_nt_field(client, db_session, make_user, authenticate_as):
    from models.wordlist import WordlistEntry
    db_session.add(WordlistEntry(password="Summer2026!", ntlm=NT))
    await db_session.flush()
    authenticate_as(await make_user(role="operator"))
    r = await client.post("/wordlist/lookup-hash", json={"hash": f"Administrator:500:{LM_EMPTY}:{NT}:::"})
    assert r.status_code == 200, r.text
    assert r.json()["found"] is True and r.json()["password"] == "Summer2026!"
    assert r.json()["hash_type"] == "ntlm"
