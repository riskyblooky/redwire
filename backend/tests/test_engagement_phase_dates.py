"""Phases still in their automatic layout follow the engagement's date
range; phases someone has adjusted stay where they were put."""

from __future__ import annotations


async def _phases(client, eid):
    r = await client.get(f"/engagements/{eid}/phases")
    assert r.status_code == 200, r.text
    return {p["phase_name"]: p for p in r.json()}


async def test_auto_phases_follow_dates_custom_ones_stay(client, make_user, authenticate_as):
    authenticate_as(await make_user(role="admin"))
    r = await client.post("/engagements", json={
        "name": "Phase follow", "client_name": "c", "engagement_type": "Red Team",
        "start_date": "2027-01-01T00:00:00",
    })
    assert r.status_code in (200, 201), r.text
    eid = r.json()["id"]
    phases = await _phases(client, eid)
    assert len(phases) == 4
    assert all(p["planned_start"] is None for p in phases.values())  # no end date yet

    # Setting the end date dates the undated phases.
    assert (await client.put(f"/engagements/{eid}", json={"end_date": "2027-01-29T00:00:00"})).status_code == 200
    phases = await _phases(client, eid)
    assert phases["SCOPING"]["planned_start"].startswith("2027-01-01")
    assert phases["REPORTING"]["planned_end"].startswith("2027-01-29")

    # Moving the range moves the automatic layout with it.
    assert (await client.put(f"/engagements/{eid}", json={
        "start_date": "2027-02-01T00:00:00", "end_date": "2027-03-01T00:00:00",
    })).status_code == 200
    phases = await _phases(client, eid)
    assert phases["SCOPING"]["planned_start"].startswith("2027-02-01")
    assert phases["PLANNING"]["planned_start"].startswith("2027-02-08")
    assert phases["REPORTING"]["planned_end"].startswith("2027-03-01")

    # Once a phase is adjusted by hand, date changes leave all of them alone.
    r = await client.put(f"/engagements/{eid}/phases", json=[
        {"id": phases["PLANNING"]["id"], "planned_end": "2027-02-20T00:00:00"},
    ])
    assert r.status_code == 200, r.text
    before = await _phases(client, eid)
    assert (await client.put(f"/engagements/{eid}", json={"end_date": "2027-04-01T00:00:00"})).status_code == 200
    assert await _phases(client, eid) == before
