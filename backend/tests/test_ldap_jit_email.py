"""LDAP: a directory entry without a mail attribute gives the user a
fallback email, not "[]", and doesn't collide with the next such user."""

from __future__ import annotations

import uuid

from ldap3 import MOCK_SYNC, Connection, Server
from sqlalchemy import select

from auth.ldap_auth import _entry_value
from models.auth_settings import AuthSetting
from models.user import User


def _entry(attrs: dict):
    server = Server("mock")
    conn = Connection(server, user="cn=admin,dc=x", password="p", client_strategy=MOCK_SYNC)
    conn.strategy.add_entry("cn=admin,dc=x", {"userPassword": "p"})
    conn.strategy.add_entry("uid=jdoe,dc=x", {"objectClass": ["inetOrgPerson"], "uid": "jdoe", **attrs})
    conn.bind()
    conn.search("dc=x", "(uid=jdoe)", attributes=["uid", "mail", "cn"])
    return conn.entries[0]


def test_missing_attribute_is_empty_not_brackets():
    e = _entry({"cn": "John Doe"})
    assert str(getattr(e, "mail", "")) == "[]"          # what the old code stored
    assert _entry_value(e, "mail") == ""
    assert _entry_value(e, "cn") == "John Doe"
    assert _entry_value(e, "notrequested") == ""


def test_multi_valued_attribute_takes_the_first():
    e = _entry({"mail": ["a@example.com", "b@example.com"]})
    assert _entry_value(e, "mail") == "a@example.com"


async def test_two_directory_users_without_mail_both_get_accounts(client, db_session, monkeypatch):
    import routers.auth as auth_router
    db_session.add(AuthSetting(key="ldap_enabled", value="true"))
    await db_session.flush()
    monkeypatch.setattr(auth_router, "authenticate_ldap",
                        lambda username, password, settings, debug=False: {"username": username, "email": "", "full_name": ""})
    names = [f"ldapu{uuid.uuid4().hex[:6]}", f"ldapu{uuid.uuid4().hex[:6]}"]
    for n in names:
        r = await client.post("/auth/login", json={"username": n, "password": "Whatever-123!"})
        assert r.status_code == 200, r.text
    emails = (await db_session.execute(select(User.email).where(User.username.in_(names)))).scalars().all()
    assert sorted(emails) == sorted(f"{n}@ldap.local" for n in names)
