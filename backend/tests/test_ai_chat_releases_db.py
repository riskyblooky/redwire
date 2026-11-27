"""The chat stream must not hold the request's DB transaction (and its pool
connection) open while it waits on the LLM or on a tool approval."""

from __future__ import annotations


async def test_request_transaction_ends_before_the_stream(client, db_session, make_user, authenticate_as,
                                                          monkeypatch):
    from routers import ai
    import utils.token_budget as tb

    events: list[str] = []

    async def _settings(db):
        await db.execute(ai.select(ai.AiSetting).limit(1))   # opens the transaction, like the real one
        return {"ai_enabled": "true", "ai_api_key": "k"}
    monkeypatch.setattr(ai, "_get_ai_settings", _settings)

    real_commit = db_session.commit

    async def _commit():
        events.append("commit")
        await real_commit()
    monkeypatch.setattr(db_session, "commit", _commit)

    async def _compact(messages, **kw):
        events.append(f"stream started (in transaction: {db_session.in_transaction()})")
        raise RuntimeError("stop here")       # the stream reports it and ends
    monkeypatch.setattr(tb, "compact_if_needed", _compact)

    authenticate_as(await make_user(role="operator"))
    r = await client.post("/ai/chat", json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200
    assert "stop here" in r.text
    assert events[:2] == ["commit", "stream started (in transaction: False)"], events
