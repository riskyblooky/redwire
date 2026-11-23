"""custom_query widget configs are checked when saved, with the same parse
and allowlist rules the data endpoint applies."""

from __future__ import annotations

GOOD = {"query": {"table": "findings", "group_by": "severity", "aggregation": "count"}}


async def test_widget_config_checked_on_save(client, make_user, authenticate_as):
    authenticate_as(await make_user(role="admin"))
    base = {"name": "w", "widget_type": "bar", "data_source": "custom_query"}
    for bad in ({"query": {"table": "users_secret", "group_by": "x"}},
                {"query": {"table": "findings", "group_by": "password_hash"}},
                {"query": {"table": "findings"}},
                {"queries": []},
                {"queries": [GOOD["query"]] * 7}):
        r = await client.post("/dashboard/widgets", json={**base, "config": bad})
        assert r.status_code == 422, (bad, r.status_code, r.text)
    r = await client.post("/dashboard/widgets", json={**base, "config": GOOD})
    assert r.status_code == 201, r.text
    wid = r.json()["id"]
    assert (await client.put(f"/dashboard/widgets/{wid}", json={"config": {"query": {"table": "nope", "group_by": "a"}}})).status_code == 422
    assert (await client.put(f"/dashboard/widgets/{wid}", json={"name": "renamed"})).status_code == 200
    # Other data sources keep free-form config.
    assert (await client.post("/dashboard/widgets", json={**base, "data_source": "findings_by_severity",
                                                          "config": {"anything": 1}})).status_code == 201
