"""Ending a user's sessions after a credential or MFA change.

Every such change (password change or reset, email change, 2FA enable or
disable, admin deactivation) has to do the same thing in the same order,
and the hand-rolled copies had drifted — some set the Redis cutoff before
deactivating API tokens, so a Redis failure left the change committed and
the rw_ tokens live.
"""
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.jwt import revoke_all_user_tokens, revoke_user_api_tokens

REVOCATION_FAILED = "Session revocation failed. Please retry."


async def end_all_sessions(
    db: AsyncSession,
    user_id: str,
    *,
    api_tokens: bool = True,
    detail: str = REVOCATION_FAILED,
) -> None:
    """Sign the user out everywhere.

    1. With ``api_tokens``, deactivate their API tokens in the caller's
       transaction, so they go with the credential change itself.
    2. Commit (the change, and the token deactivation).
    3. Set the Redis revocation cutoff: every access/refresh token issued
       so far stops working. If that fails, raise 500 — the change is in
       place but old sessions would live, which must not pass silently
       (GHSA-832g-v288-v593).

    ``api_tokens=False`` is for deactivation and "sign out everywhere":
    API-token auth already refuses inactive users, and revoke-sessions
    leaves API tokens to be revoked individually.

    To keep the caller signed in afterwards, mint the new pair *after*
    this returns (the cutoff is in milliseconds, so it survives).
    """
    if api_tokens:
        await revoke_user_api_tokens(db, user_id)
    await db.commit()
    if not revoke_all_user_tokens(user_id):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)
