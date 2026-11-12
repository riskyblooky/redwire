from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
import os
import redis
import logging
import time
import uuid

logger = logging.getLogger(__name__)

_INSECURE_DEFAULT_SECRET = "your-secret-key-change-in-production"
_MIN_SECRET_LENGTH = 32
SECRET_KEY = os.getenv("JWT_SECRET", _INSECURE_DEFAULT_SECRET)
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_HOURS = int(os.getenv("REFRESH_TOKEN_EXPIRE_HOURS", "24"))



def validate_secret() -> None:
    """Fail closed at startup on a missing, published-default or short
    JWT_SECRET: anyone who knows the signing key can mint an admin token."""
    if not SECRET_KEY or SECRET_KEY == _INSECURE_DEFAULT_SECRET or len(SECRET_KEY) < _MIN_SECRET_LENGTH:
        raise RuntimeError(
            f"JWT_SECRET is unset, the published default, or shorter than {_MIN_SECRET_LENGTH} "
            "characters. Set a strong random JWT_SECRET (e.g. `openssl rand -hex 32`) in .env."
        )

# Redis connection for token blacklist
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
_redis_client: Optional[redis.Redis] = None
_REDIS_TIMEOUT_S = float(os.getenv("REDIS_TIMEOUT_S", "1.5"))


def _get_redis() -> Optional[redis.Redis]:
    """Get or create Redis client for token blacklist.
    
    Does NOT cache None — if Redis was temporarily down, the next call
    will retry the connection instead of being stuck in fail-closed forever.
    """
    global _redis_client
    if _redis_client is not None:
        # No ping per call: it doubled the round trips of every request's
        # blacklist check. The pool health-checks idle connections and
        # reconnects after an error; a failing command raises, and every
        # caller fails closed on that.
        return _redis_client
    try:
        # Bounded timeouts: this runs on every authenticated request, and an
        # unbounded read against a hung Redis stalled the request forever.
        client = redis.from_url(
            REDIS_URL, decode_responses=True,
            socket_connect_timeout=_REDIS_TIMEOUT_S, socket_timeout=_REDIS_TIMEOUT_S,
            health_check_interval=30,
        )
        client.ping()
        _redis_client = client
        return _redis_client
    except Exception as e:
        logger.warning(f"Redis connection failed for token blacklist: {e}")
        return None


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    # Preserve explicit token type (e.g. "password_reset") if set in data,
    # otherwise default to "access"
    token_type = to_encode.pop("type", "access")
    # jti gives each token a stable identity that survives base64 padding —
    # the per-token blacklist keys on it instead of the raw token bytes.
    # GHSA-832g-v288-v593.
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": token_type,
        "jti": str(uuid.uuid4()),
    })
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict) -> str:
    """Create a JWT refresh token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=REFRESH_TOKEN_EXPIRE_HOURS)
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "refresh",
        "jti": str(uuid.uuid4()),
    })
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_token(token: str) -> Optional[dict]:
    """Decode and verify a JWT token.

    Verifies signature using the pinned algorithm (prevents algorithm confusion attacks).
    Requires 'sub', 'type', 'jti', and 'exp' claims to be present.
    Validates expiration automatically.

    The jti requirement also acts as a deploy-time invalidation: any token
    issued before the jti rollout lacks the claim and is rejected, forcing
    all active sessions to re-authenticate on first request after upgrade.
    GHSA-832g-v288-v593.
    """
    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            options={
                "require_exp": True,
                "require_sub": True,
                "verify_exp": True,
                "verify_signature": True,
            }
        )
        # Additional checks: require 'type' and 'jti' claims
        if "type" not in payload or "jti" not in payload:
            return None
        return payload
    except JWTError:
        return None


def blacklist_token(token: str) -> bool:
    """Add a token to the per-token blacklist, keyed on its jti claim.

    Returns True on success, False if Redis is unavailable or the token is
    not blacklistable (missing jti or malformed). The caller MUST surface a
    False return to the client — a silently-failed revocation looks like
    success but leaves the token live. GHSA-832g-v288-v593.
    """
    r = _get_redis()
    if r is None:
        logger.error("Cannot blacklist token: Redis unavailable")
        return False

    try:
        # Decode without exp verification — an expired token still needs
        # revocation if a caller asks for it (callers verify freshness).
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"verify_exp": False}
        )
        jti = payload.get("jti")
        if not jti:
            logger.error("Cannot blacklist token: missing jti claim")
            return False
        exp = payload.get("exp")
        if exp:
            # TTL = time until token expires (no point keeping it longer)
            ttl = max(int(exp - datetime.utcnow().timestamp()), 1)
        else:
            # Fallback: blacklist for 24 hours
            ttl = 86400

        r.setex(f"token_blacklist:{jti}", ttl, "1")
        return True
    except Exception as e:
        logger.error(f"Failed to blacklist token: {e}")
        return False


def revoke_all_user_tokens(user_id: str) -> bool:
    """Revokes all existing tokens for a given user by setting a timestamp in Redis.
    
    Any token issued before this timestamp will be considered invalid.
    """
    r = _get_redis()
    if r is None:
        logger.error("Cannot revoke user tokens: Redis unavailable")
        return False
    
    try:
        # TTL matches our max refresh token lifetime (hours -> seconds)
        ttl = REFRESH_TOKEN_EXPIRE_HOURS * 3600
        # Whole-second epoch: JWT iat is whole seconds (python-jose truncates),
        # so a fractional cutoff made tokens issued later in the same second
        # — e.g. the fresh pair force-change-password hands out right after
        # revoking — compare as older than the cutoff and get rejected.
        r.setex(f"token_revocation:{user_id}", ttl, str(int(time.time())))
        return True
    except Exception as e:
        logger.error(f"Failed to revoke user tokens: {e}")
        return False


async def revoke_user_api_tokens(db, user_id: str) -> None:
    """Deactivate every API token the user holds: the long-lived-bearer
    counterpart of revoke_all_user_tokens, for credential changes. The
    caller commits."""
    from sqlalchemy import update
    from models.api_token import ApiToken
    await db.execute(
        update(ApiToken)
        .where(ApiToken.user_id == user_id, ApiToken.is_active == True)  # noqa: E712
        .values(is_active=False)
    )


def is_token_blacklisted(token: str) -> bool:
    """Check if a token has been blacklisted.

    Checks both the per-token blacklist (keyed on jti) and the per-user
    revocation cutoff. Fails CLOSED on any error — revoked tokens must not
    be silently accepted under a Redis hiccup or decode fault.
    GHSA-832g-v288-v593.
    """
    r = _get_redis()
    if r is None:
        logger.critical("Redis unavailable — failing closed on token blacklist check")
        return True

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], options={"verify_exp": False})

        # 1. Per-token blacklist, keyed on jti so base64 padding can't bypass it.
        jti = payload.get("jti")
        if jti and r.exists(f"token_blacklist:{jti}") > 0:
            return True

        # 2. Per-user revocation cutoff
        user_id = payload.get("sub")
        if user_id:
            revocation_ts = r.get(f"token_revocation:{user_id}")
            if revocation_ts:
                iat = payload.get("iat")
                # If token has no iat, or was issued before the revocation timestamp, reject it
                if not iat or float(iat) < float(revocation_ts):
                    return True

        return False
    except Exception as e:
        # Any exception (Redis fault, decode error, anything) means we
        # can't tell — fail closed.
        logger.critical(f"Failing closed on token blacklist check: {e}")
        return True
