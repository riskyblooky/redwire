"""API-token use is recorded at most once a minute per token, not with a
write + commit on every request."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta


async def test_last_used_is_throttled(db_session, make_user):
    from auth.dependencies import _resolve_api_token
    from models.api_token import ApiToken
    user = await make_user()
    raw = "rw_" + uuid.uuid4().hex
    tok = ApiToken(id=str(uuid.uuid4()), name="ci", token_hash=hashlib.sha256(raw.encode()).hexdigest(),
                   token_prefix=raw[:7], permission="rw", user_id=user.id, is_active=True)
    db_session.add(tok)
    await db_session.flush()

    await _resolve_api_token(raw, db_session)
    first = tok.last_used_at
    assert first is not None
    await _resolve_api_token(raw, db_session)
    assert tok.last_used_at == first          # within the minute: no write

    tok.last_used_at = datetime.utcnow() - timedelta(minutes=2)
    await db_session.flush()
    await _resolve_api_token(raw, db_session)
    assert tok.last_used_at > first - timedelta(seconds=1) and tok.last_used_at > datetime.utcnow() - timedelta(seconds=30)
