"""System widgets are seeded at startup, never by the widget list GET."""

from __future__ import annotations

from sqlalchemy import select, update


async def test_list_never_seeds(client, db_session, make_user, authenticate_as, monkeypatch):
    from routers import dashboard_widgets as dw
    from models.dashboard_widget import DashboardWidget

    await dw._seed_system_widgets(db_session)
    first = dw.SYSTEM_WIDGETS[0]["id"]
    await db_session.execute(update(DashboardWidget).where(DashboardWidget.id == first).values(is_active=False))
    await db_session.flush()

    async def _boom(db):
        raise AssertionError("GET /widgets seeded")
    monkeypatch.setattr(dw, "_seed_system_widgets", _boom)

    authenticate_as(await make_user(role="operator"))
    r = await client.get("/dashboard/widgets")
    assert r.status_code == 200, r.text
    assert first not in {w["id"] for w in r.json()}


async def test_seeder_is_idempotent_and_keeps_deactivations(db_session):
    from routers import dashboard_widgets as dw
    from models.dashboard_widget import DashboardWidget

    await dw._seed_system_widgets(db_session)
    first = dw.SYSTEM_WIDGETS[0]["id"]
    await db_session.execute(update(DashboardWidget).where(DashboardWidget.id == first).values(is_active=False))
    assert await dw._seed_system_widgets(db_session) == 0
    active = (await db_session.execute(select(DashboardWidget.is_active).where(DashboardWidget.id == first))).scalar_one()
    assert active is False
