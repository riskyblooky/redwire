"""Infra vault list/write responses carry no secrets; GET .../reveal does
and records a Security Center event."""

from __future__ import annotations

import uuid

from sqlalchemy import select


async def _item_with_secret(db, owner):
    from models.infra_item import InfraItem
    from models.infra_vault_item import InfraVaultItem
    item = InfraItem(id=str(uuid.uuid4()), name="c2-primary")
    db.add(item)
    await db.flush()
    vi = InfraVaultItem(infra_item_id=item.id, name="root", item_type="CREDENTIAL", username="root",
                        password="hunter2-c2", note="ssh port 2222", created_by=owner.id)
    db.add(vi)
    await db.flush()
    return item, vi


async def test_list_hides_secrets_reveal_returns_and_logs(client, db_session, make_user, authenticate_as,
                                                          security_events_on, monkeypatch):
    import routers.infra
    from models.security_event import SecurityEvent
    monkeypatch.setattr(routers.infra, "should_log_vault_access", lambda *_: True)
    admin = await make_user(role="admin")
    item, vi = await _item_with_secret(db_session, admin)
    authenticate_as(admin)

    (row,) = (await client.get(f"/infra/items/{item.id}/vault")).json()
    assert "password" not in row and "note" not in row
    assert row["has_password"] and row["has_note"] and row["username"] == "root"

    r = await client.get(f"/infra/items/{item.id}/vault/{vi.id}/reveal")
    assert r.status_code == 200
    assert (r.json()["password"], r.json()["note"]) == ("hunter2-c2", "ssh port 2222")

    events = (await security_events_on.execute(
        select(SecurityEvent).where(SecurityEvent.event_type == "infra_vault_accessed"))).scalars().all()
    assert len(events) == 1 and events[0].details["vault_item_id"] == vi.id


async def test_reveal_requires_vault_access(client, db_session, make_user, authenticate_as):
    item, vi = await _item_with_secret(db_session, await make_user(role="admin"))
    authenticate_as(await make_user(role="operator"))
    assert (await client.get(f"/infra/items/{item.id}/vault/{vi.id}/reveal")).status_code == 403
