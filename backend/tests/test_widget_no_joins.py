"""The widget query builder has no join support: join_tables is ignored
(it used to LEFT JOIN tables none of whose columns could be used, which
only multiplied rows under the aggregate) and the schema lists no joins."""

from __future__ import annotations


async def test_join_tables_is_ignored_and_not_advertised(client, make_user, authenticate_as):
    authenticate_as(await make_user(role="admin"))
    base = {"table": "findings", "group_by": "severity", "aggregation": "count", "value_column": "id"}
    plain = await client.post("/dashboard/widgets/query-preview", json=base)
    joined = await client.post("/dashboard/widgets/query-preview", json={**base, "join_tables": ["engagements"]})
    assert plain.status_code == joined.status_code == 200, joined.text
    assert plain.json()["data"] == joined.json()["data"]

    schema = (await client.get("/dashboard/widgets/query-schema")).json()
    assert all("joins" not in t for t in schema["schema"].values())

    from routers.dashboard_widgets import QueryPreviewRequest
    assert "join_tables" not in QueryPreviewRequest.model_fields
