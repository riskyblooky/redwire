"""SAML sign-in end to end: /auth/saml/login issues the AuthnRequest and its
binding cookie, a test IdP signs an assertion answering it, and /auth/saml/acs
validates it with python3-saml for real (signature, audience, recipient,
InResponseTo, replay cache), provisions the user and hands back a working
session. The negative cases go through the same path."""

from __future__ import annotations

import base64
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import delete, select

pytest.importorskip("onelogin.saml2.utils")

IDP = "https://idp.test/metadata"
SP = "https://redwire.test/saml-sp"


@pytest.fixture(scope="module")
def idp_keys():
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "idp.test")])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=30))
            .sign(key, hashes.SHA256()))
    key_pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption()).decode()
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    return key_pem, cert_pem


@pytest.fixture
async def saml_on(db_session, idp_keys, monkeypatch):
    import auth.saml_auth as saml_auth
    from models.auth_settings import AuthSetting

    # The ACS validates against BACKEND_URL; the SP settings use the module's
    # BASE_URL. Keep them the same, whatever the environment says.
    monkeypatch.setenv("BACKEND_URL", saml_auth.BASE_URL)
    monkeypatch.setenv("FRONTEND_URL", "https://app.test")
    cert_body = "".join(l for l in idp_keys[1].splitlines() if "CERTIFICATE" not in l)
    rows = {
        "saml_enabled": "true", "saml_idp_entity_id": IDP,
        "saml_idp_sso_url": "https://idp.test/sso", "saml_idp_x509_cert": cert_body,
        "saml_sp_entity_id": SP,
    }
    await db_session.execute(delete(AuthSetting).where(AuthSetting.key.in_(list(rows))))
    for k, v in rows.items():
        db_session.add(AuthSetting(key=k, value=v, is_encrypted=False))
    await db_session.commit()
    yield saml_auth.BASE_URL + "/auth/saml/acs"
    await db_session.execute(delete(AuthSetting).where(AuthSetting.key.in_(list(rows))))
    await db_session.commit()


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _response(idp_keys, acs, request_id, name_id, email, *, audience=SP, tamper=None):
    """A Response whose Assertion is signed by the test IdP (the SP requires
    signed assertions)."""
    from onelogin.saml2.constants import OneLogin_Saml2_Constants as C
    from onelogin.saml2.utils import OneLogin_Saml2_Utils

    now = datetime.now(timezone.utc)
    aid, rid = "_" + uuid.uuid4().hex, "_" + uuid.uuid4().hex
    assertion = f"""<saml:Assertion xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" ID="{aid}" Version="2.0" IssueInstant="{_iso(now)}">
<saml:Issuer>{IDP}</saml:Issuer>
<saml:Subject><saml:NameID Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress">{name_id}</saml:NameID>
<saml:SubjectConfirmation Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
<saml:SubjectConfirmationData InResponseTo="{request_id}" NotOnOrAfter="{_iso(now + timedelta(minutes=5))}" Recipient="{acs}"/>
</saml:SubjectConfirmation></saml:Subject>
<saml:Conditions NotBefore="{_iso(now - timedelta(minutes=1))}" NotOnOrAfter="{_iso(now + timedelta(minutes=5))}">
<saml:AudienceRestriction><saml:Audience>{audience}</saml:Audience></saml:AudienceRestriction></saml:Conditions>
<saml:AuthnStatement AuthnInstant="{_iso(now)}" SessionIndex="{aid}"><saml:AuthnContext><saml:AuthnContextClassRef>urn:oasis:names:tc:SAML:2.0:ac:classes:Password</saml:AuthnContextClassRef></saml:AuthnContext></saml:AuthnStatement>
<saml:AttributeStatement>
<saml:Attribute Name="email"><saml:AttributeValue>{email}</saml:AttributeValue></saml:Attribute>
<saml:Attribute Name="displayName"><saml:AttributeValue>Sam L User</saml:AttributeValue></saml:Attribute>
</saml:AttributeStatement></saml:Assertion>"""
    signed = OneLogin_Saml2_Utils.add_sign(assertion, idp_keys[0], idp_keys[1],
                                           sign_algorithm=C.RSA_SHA256, digest_algorithm=C.SHA256)
    signed = signed.decode() if isinstance(signed, bytes) else signed
    signed = signed.split("?>", 1)[1] if signed.startswith("<?xml") else signed
    if tamper:
        signed = tamper(signed)
    xml = f"""<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" ID="{rid}" Version="2.0" IssueInstant="{_iso(now)}" Destination="{acs}" InResponseTo="{request_id}">
<saml:Issuer>{IDP}</saml:Issuer>
<samlp:Status><samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/></samlp:Status>{signed}</samlp:Response>"""
    return base64.b64encode(xml.encode()).decode()


async def _start_login(client):
    """GET /auth/saml/login; returns (binding cookie, the AuthnRequest id)."""
    from auth.jwt import decode_token

    r = await client.get("/auth/saml/login", follow_redirects=False)
    assert r.status_code in (302, 307), r.text
    assert urlparse(r.headers["location"]).netloc == "idp.test"
    cookie = r.cookies.get("saml_request_id")
    assert cookie, "login must set the request-binding cookie"
    return cookie, decode_token(cookie)["saml_req"]


async def _acs(client, cookie, saml_response):
    client.cookies.clear()
    if cookie:
        client.cookies.set("saml_request_id", cookie)
    return await client.post("/auth/saml/acs", data={"SAMLResponse": saml_response}, follow_redirects=False)


@pytest.fixture
def no_blacklist(monkeypatch):
    import auth.dependencies as deps
    monkeypatch.setattr(deps, "is_token_blacklisted", lambda _t: False)


async def test_saml_login_provisions_user_and_session(client, db_session, saml_on, idp_keys, no_blacklist):
    from models.user import User

    name_id = f"sam-{uuid.uuid4().hex[:8]}@corp.test"
    cookie, req_id = await _start_login(client)
    r = await _acs(client, cookie, _response(idp_keys, saml_on, req_id, name_id, name_id))
    assert r.status_code == 302, r.text
    loc = urlparse(r.headers["location"])
    assert (loc.scheme, loc.netloc, loc.path) == ("https", "app.test", "/sso/callback")
    token = parse_qs(loc.fragment)["access_token"][0]
    assert "refresh_token=" in r.headers.get("set-cookie", "")

    user = (await db_session.execute(select(User).where(User.saml_subject == name_id))).scalar_one()
    assert user.auth_provider == "saml" and user.email == name_id and user.full_name == "Sam L User"
    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["id"] == user.id


async def test_saml_response_to_another_login_is_refused(client, saml_on, idp_keys):
    """A Response answering an earlier AuthnRequest (InResponseTo doesn't
    match the request bound in this browser's cookie)."""
    name_id = f"old-{uuid.uuid4().hex[:8]}@corp.test"
    _cookie, old_req = await _start_login(client)
    cookie, _new_req = await _start_login(client)
    r = await _acs(client, cookie, _response(idp_keys, saml_on, old_req, name_id, name_id))
    assert r.status_code == 401


async def test_saml_replayed_assertion_is_refused(client, saml_on, idp_keys):
    name_id = f"rep-{uuid.uuid4().hex[:8]}@corp.test"
    cookie, req_id = await _start_login(client)
    resp = _response(idp_keys, saml_on, req_id, name_id, name_id)
    assert (await _acs(client, cookie, resp)).status_code == 302
    assert (await _acs(client, cookie, resp)).status_code == 401


@pytest.mark.parametrize("case", ["tampered", "wrong_audience", "foreign_key", "no_cookie"])
async def test_saml_rejects_bad_responses(client, db_session, saml_on, idp_keys, case):
    from models.user import User

    name_id = f"bad-{uuid.uuid4().hex[:8]}@corp.test"
    cookie, req_id = await _start_login(client)
    keys, kw = idp_keys, {}
    if case == "tampered":
        kw["tamper"] = lambda x: x.replace(f">{name_id}</saml:AttributeValue>", ">admin@corp.test</saml:AttributeValue>")
    elif case == "wrong_audience":
        kw["audience"] = "https://someone-else.test"
    elif case == "foreign_key":
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
        keys = (other, idp_keys[1])  # signed with a key the IdP cert doesn't match
    r = await _acs(client, None if case == "no_cookie" else cookie,
                   _response(keys, saml_on, req_id, name_id, name_id, **kw))
    assert r.status_code == (400 if case == "no_cookie" else 401), r.text
    assert (await db_session.execute(select(User).where(User.saml_subject == name_id))).scalar_one_or_none() is None
