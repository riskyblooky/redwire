"""Global search query language: operators, scopes, NOT on empty fields, relevance."""

from __future__ import annotations

import uuid

from routers.search import AndNode, CategoryNode, FieldNode, OrNode, TextNode, parse_query
from tests.test_authz_boundaries import _make_engagement, _make_finding


def test_lowercase_and_or_not_are_words():
    assert parse_query("remote code or command") == AndNode(children=[
        TextNode("remote"), TextNode("code"), TextNode("or"), TextNode("command")])
    assert isinstance(parse_query("XSS OR CSRF"), OrNode)


def test_engagement_and_client_with_a_value_filter():
    assert parse_query("engagement:acme") == FieldNode("engagement", "acme")
    assert parse_query("CLIENT:corp") == FieldNode("client", "corp")
    assert parse_query("finding:ssrf") == CategoryNode("finding", "ssrf")


def test_bare_category_scopes():
    assert parse_query("asset: engagement:acme") == AndNode(children=[
        CategoryNode("asset", ""), FieldNode("engagement", "acme")])
    assert parse_query("vault:") == CategoryNode("vault", "")


def _cats(r):
    return {c["category"]: [i["id"] for i in c["items"]] for c in r.json()["results"]}


async def test_engagement_filter_and_bare_scope_over_http(client, db_session, make_user, authenticate_as):
    admin = await make_user(role="admin")
    authenticate_as(admin)
    tag = uuid.uuid4().hex[:8]
    acme = await _make_engagement(db_session, name=f"acme-{tag}")
    other = await _make_engagement(db_session, name=f"other-{tag}")
    f1 = await _make_finding(db_session, acme, title=f"t-{tag} in acme")
    f2 = await _make_finding(db_session, other, title=f"t-{tag} elsewhere")

    cats = _cats(await client.get("/search", params={"q": f"finding: engagement:acme-{tag}"}))
    assert set(cats) == {"findings"}
    assert cats["findings"] == [f1.id]
    assert f2.id not in cats["findings"]


async def test_not_keeps_rows_whose_field_is_empty(client, db_session, make_user, authenticate_as):
    admin = await make_user(role="admin")
    authenticate_as(admin)
    tag = uuid.uuid4().hex[:8]
    eng = await _make_engagement(db_session)
    no_impact = await _make_finding(db_session, eng, title=f"n-{tag}", impact=None)
    has_word = await _make_finding(db_session, eng, title=f"n-{tag} kerberos")

    cats = _cats(await client.get("/search", params={"q": f"finding:n-{tag} NOT kerberos"}))
    assert no_impact.id in cats.get("findings", [])
    assert has_word.id not in cats.get("findings", [])


async def test_relevance_ranks_beyond_the_most_recent_rows(client, db_session, make_user, authenticate_as):
    admin = await make_user(role="admin")
    authenticate_as(admin)
    tag = uuid.uuid4().hex[:8]
    eng = await _make_engagement(db_session)
    # Best match is the OLDEST: title, description and impact all contain the term.
    best = await _make_finding(db_session, eng, title=f"r{tag}", description=f"r{tag}", impact=f"r{tag}")
    from datetime import datetime, timedelta
    best.updated_at = datetime.utcnow() - timedelta(days=30)
    for i in range(3):
        await _make_finding(db_session, eng, title=f"r{tag} {i}", description="x", impact="x")
    await db_session.flush()

    cats = _cats(await client.get("/search", params={"q": f"r{tag}", "limit": 2, "sort": "relevance"}))
    assert cats["findings"][0] == best.id
    assert len(cats["findings"]) == 2
