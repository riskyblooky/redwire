from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
import os
import hashlib
import redis
import logging

logger = logging.getLogger(__name__)

SECRET_KEY = os.getenv("JWT_SECRET", "your-secret-key-change-in-production")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_HOURS = int(os.getenv("REFRESH_TOKEN_EXPIRE_HOURS", "24"))

# Warn loudly if using the insecure default secret
if SECRET_KEY == "your-secret-key-change-in-production":
    logger.critical(
        "JWT_SECRET is set to the insecure default! "
        "Set a strong JWT_SECRET environment variable before deploying."
    )

# Redis connection for token blacklist
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
_redis_client: Optional[redis.Redis] = None


def _get_redis() -> Optional[redis.Redis]:
    """Get or create Redis client for token blacklist.
    
    Does NOT cache None — if Redis was temporarily down, the next call
    will retry the connection instead of being stuck in fail-closed forever.
    """
    global _redis_client
    if _redis_client is not None:
        try:
            _redis_client.ping()
            return _redis_client
        except Exception:
            # Connection went stale, force reconnect
            _redis_client = None
    try:
        client = redis.from_url(REDIS_URL, decode_responses=True)
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
    to_encode.update({"exp": expire, "iat": datetime.utcnow(), "type": token_type})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict) -> str:
    """Create a JWT refresh token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=REFRESH_TOKEN_EXPIRE_HOURS)
    to_encode.update({"exp": expire, "iat": datetime.utcnow(), "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_token(token: str) -> Optional[dict]:
    """Decode and verify a JWT token.
    
    Verifies signature using the pinned algorithm (prevents algorithm confusion attacks).
    Requires 'sub', 'type', and 'exp' claims to be present.
    Validates expiration automatically.
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
        # Additional check: require 'type' claim
        if "type" not in payload:
            return None
        return payload
    except JWTError:
        return None


def _token_fingerprint(token: str) -> str:
    """Create a short fingerprint of a token for Redis storage.
    
    We store a hash instead of the full token to minimize what's in Redis.
    """
    return hashlib.sha256(token.encode()).hexdigest()


def blacklist_token(token: str) -> bool:
    """Add a token to the blacklist.
    
    The token is stored in Redis with a TTL matching its remaining lifetime.
    Returns True if successfully blacklisted, False if Redis is unavailable.
    """
    r = _get_redis()
    if r is None:
        logger.error("Cannot blacklist token: Redis unavailable")
        return False
    
    try:
        # Decode without verification to get expiration (token is already verified by caller)
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"verify_exp": False}  # May be expired but still need to blacklist
        )
        exp = payload.get("exp")
        if exp:
            # TTL = time until token expires (no point keeping it longer)
            ttl = max(int(exp - datetime.utcnow().timestamp()), 1)
        else:
            # Fallback: blacklist for 24 hours
            ttl = 86400
        
        fingerprint = _token_fingerprint(token)
        r.setex(f"token_blacklist:{fingerprint}", ttl, "1")
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
        # Store current timestamp
        r.setex(f"token_revocation:{user_id}", ttl, str(datetime.utcnow().timestamp()))
        return True
    except Exception as e:
        logger.error(f"Failed to revoke user tokens: {e}")
        return False


def is_token_blacklisted(token: str) -> bool:
    """Check if a token has been blacklisted.
    
    Checks both specific token blacklist and user-wide revocation.
    Fails CLOSED if Redis is unavailable — revoked tokens must not be accepted.
    """
    r = _get_redis()
    if r is None:
        logger.critical("Redis unavailable — failing closed on token blacklist check")
        return True
    
    try:
        # 1. Check exact token fingerprint blacklist
        fingerprint = _token_fingerprint(token)
        if r.exists(f"token_blacklist:{fingerprint}") > 0:
            return True
            
        # 2. Check user-wide revocation
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], options={"verify_exp": False})
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
        logger.warning(f"Failed to check token blacklist: {e}")
        return False
