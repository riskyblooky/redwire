"""Custom-query widgets: enum labels, newest time buckets, relative prior ranges."""

from __future__ import annotations

from datetime import datetime, timedelta

from models.finding import Severity
from tests.test_authz_boundaries import _make_engagement, _make_finding

PREVIEW = "/dashboard/widgets/query-preview"


async def _findings_on_days(db, days_ago: list[int], **kw):
    eng = await _make_engagement(db)
    now = datetime.utcnow()
    for d in days_ago:
        f = await _make_finding(db, eng, **kw)
        f.created_at = now - timedelta(days=d)
    await db.flush()
    return eng


async def test_labels_are_enum_values(client, db_session, make_user, authenticate_as):
    authenticate_as(await make_user(role="admin"))
    await _findings_on_days(db_session, [0], severity=Severity.CRITICAL)
    r = await client.post(PREVIEW, json={"table": "findings", "group_by": "severity",
                                         "aggregation": "count", "value_column": "id"})
    assert r.status_code == 200, r.text
    labels = {d["label"] for d in r.json()["data"]}
    assert "CRITICAL" in labels and not any(l.startswith("Severity.") for l in labels)


async def test_time_series_limit_keeps_the_newest_buckets(client, db_session, make_user, authenticate_as):
    authenticate_as(await make_user(role="admin"))
    await _findings_on_days(db_session, [0, 1, 2, 300, 301, 302], severity=Severity.HIGH)
    newest = (datetime.utcnow()).date().isoformat()
    for series in (None, "severity"):
        body = {"table": "findings", "group_by": "severity", "aggregation": "count", "value_column": "id",
                "date_column": "created_at", "time_bucket": "day", "limit": 3}
        if series:
            body["series_by"] = series
        r = await client.post(PREVIEW, json=body)
        assert r.status_code == 200, r.text
        dates = [d["date"][:10] for d in r.json()["data"]]
        assert len(dates) == 3, (series, dates)
        assert dates == sorted(dates), (series, dates)
        assert dates[-1] == newest, (series, dates)
        if series:
            assert all(d.get("HIGH") for d in r.json()["data"]), r.json()["data"]


async def test_prior_7d_is_the_week_before_last(client, db_session, make_user, authenticate_as):
    authenticate_as(await make_user(role="admin"))
    eng = await _findings_on_days(db_session, [1, 9, 10, 20], severity=Severity.LOW)
    body = {"table": "findings", "group_by": "engagement_id", "aggregation": "count", "value_column": "id",
            "date_column": "created_at", "date_range": "prior_7d",
            "filters": [{"column": "engagement_id", "operator": "eq", "value": eng.id}]}
    r = await client.post(PREVIEW, json=body)
    assert r.status_code == 200, r.text
    assert sum(d["value"] for d in r.json()["data"]) == 2


def test_system_delta_widget_has_no_fixed_dates():
    from routers.dashboard_widgets import SYSTEM_WIDGETS
    w = next(w for w in SYSTEM_WIDGETS if w["id"] == "sys-findings-week-delta")
    prior = w["config"]["queries"][1]
    assert prior["date_range"] == "prior_7d"
    assert "date_start" not in prior and "date_end" not in prior
