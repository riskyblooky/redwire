"""
Hash computation utilities and Bloom filter service for wordlist lookups.

Supports NTLM, MD5, SHA-1 for rainbow table reverse-lookups.
bcrypt and krb5tgs are salted — cannot be reversed from hash alone.
"""
import hashlib
import struct
import logging
import asyncio
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# Hash computation
# ═══════════════════════════════════════════════════════════════════

def compute_ntlm(password: str) -> str:
    """Compute NTLM hash (MD4 of UTF-16LE encoded password)."""
    pw_bytes = password.encode("utf-16-le")
    try:
        return hashlib.new("md4", pw_bytes, usedforsecurity=False).hexdigest()
    except ValueError:
        # MD4 completely unavailable — skip NTLM
        return ""


def compute_md5(password: str) -> str:
    """Compute MD5 hash of password."""
    return hashlib.md5(password.encode("utf-8", errors="replace")).hexdigest()


def compute_sha1(password: str) -> str:
    """Compute SHA-1 hash of password."""
    return hashlib.sha1(password.encode("utf-8", errors="replace")).hexdigest()


def compute_all_hashes(password: str) -> dict:
    """Compute all supported hash types for a password."""
    return {
        "ntlm": compute_ntlm(password),
        "md5": compute_md5(password),
        "sha1": compute_sha1(password),
    }


# ═══════════════════════════════════════════════════════════════════
# Hash type identification
# ═══════════════════════════════════════════════════════════════════

def identify_hash_type(hash_str: str) -> Optional[str]:
    """
    Identify a hash type from its format.
    Returns: 'ntlm', 'md5', 'sha1', 'bcrypt', 'krb5tgs', or None.
    """
    if not hash_str:
        return None

    h = hash_str.strip()

    # bcrypt
    if h.startswith(("$2b$", "$2a$", "$2y$")):
        return "bcrypt"

    # Kerberos TGS
    if h.startswith("$krb5tgs$"):
        return "krb5tgs"

    # Check hex hashes by length
    try:
        int(h, 16)  # Valid hex?
    except ValueError:
        return None

    if len(h) == 32:
        # Could be MD5 or NTLM — we'll try both during lookup
        return "md5_or_ntlm"
    elif len(h) == 40:
        return "sha1"

    return None


# ═══════════════════════════════════════════════════════════════════
# Bloom Filter Service
# ═══════════════════════════════════════════════════════════════════

def bloom_positions(item: str, bit_count: int, num_hashes: int) -> list:
    """Bit positions for ``item`` (double hashing with MD5+SHA1)."""
    h1 = int(hashlib.md5(item.encode("utf-8", errors="replace")).hexdigest(), 16)
    h2 = int(hashlib.sha1(item.encode("utf-8", errors="replace")).hexdigest(), 16)
    return [(h1 + i * h2) % bit_count for i in range(num_hashes)]


def _redis_bit(pos: int) -> int:
    """Redis GETBIT/SETBIT offset for our LSB-first bit layout (Redis numbers
    bits MSB-first within each byte)."""
    return (pos // 8) * 8 + (7 - pos % 8)


class BloomFilter:
    """
    Simple but efficient Bloom filter using multiple hash functions.
    
    For 14M items with 0.1% false positive rate:
    - bits needed: ~20M bytes (161M bits)
    - hash functions: 10
    """

    def __init__(self, capacity: int = 20_000_000, fp_rate: float = 0.001):
        import math
        self.capacity = capacity
        self.fp_rate = fp_rate

        # Calculate optimal bit array size and number of hash functions
        if capacity > 0:
            self.bit_count = int(-capacity * math.log(fp_rate) / (math.log(2) ** 2))
            self.num_hashes = max(1, int((self.bit_count / capacity) * math.log(2)))
        else:
            self.bit_count = 1
            self.num_hashes = 1

        # Use bytearray for compact storage
        self.byte_count = (self.bit_count + 7) // 8
        self.bit_array = bytearray(self.byte_count)
        self.count = 0

    def _get_bit_positions(self, item: str) -> list:
        return bloom_positions(item, self.bit_count, self.num_hashes)

    def add(self, item: str):
        """Add an item to the filter."""
        for pos in self._get_bit_positions(item):
            byte_idx = pos // 8
            bit_idx = pos % 8
            self.bit_array[byte_idx] |= (1 << bit_idx)
        self.count += 1

    def check(self, item: str) -> bool:
        """Check if an item might be in the filter. False = definitely not. True = probably yes."""
        for pos in self._get_bit_positions(item):
            byte_idx = pos // 8
            bit_idx = pos % 8
            if not (self.bit_array[byte_idx] & (1 << bit_idx)):
                return False
        return True


_BITS_KEY = "rw:bloom:bits"
_META_KEY = "rw:bloom:meta"
_LOADING_KEY = "rw:bloom:loading"
_LOADING_TTL = 3600


class BloomFilterService:
    """
    Wordlist Bloom filter. Loaded from the database on startup and rebuilt
    when wordlists change.

    Shared mode (Redis reachable): the filter's bytes live in Redis
    (``rw:bloom:bits`` + ``rw:bloom:meta``), so every backend worker reads
    the same copy. One worker builds it (``rw:bloom:loading`` doubles as the
    build lock), checks read ``num_hashes`` bits with GETBIT, imports SETBIT
    in batches, and rebuilds swap bits and metadata in one MULTI. Workers
    keep no local copy.

    Local mode (no Redis): the filter is an in-process bytearray, as in
    single-worker deployments.
    """

    _instance = None
    _bloom: Optional[BloomFilter] = None
    _loaded: bool = False
    _loading: bool = False
    _count: int = 0

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    # ── local-mode accessors (kept for callers / tests) ───────────────────
    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def is_loading(self) -> bool:
        return self._loading

    @property
    def count(self) -> int:
        return self._count

    def check_password(self, password: str) -> bool:
        """Local-mode check. Prefer ``check_password_async``."""
        if not self._loaded or self._bloom is None:
            return False
        return self._bloom.check(password)

    # ── shared mode ────────────────────────────────────────────────────────
    @staticmethod
    def _shared_sync():
        from utils.cluster import sync_redis
        return sync_redis()

    @staticmethod
    def _decode_meta(raw: dict) -> Optional[dict]:
        if not raw:
            return None
        m = {(k.decode() if isinstance(k, bytes) else k): int(v) for k, v in raw.items()}
        if not m.get("bit_count") or not m.get("num_hashes"):
            return None
        return m

    async def check_password_async(self, password: str) -> bool:
        from utils.cluster import async_redis
        r = await async_redis()
        if r is None:
            return self.check_password(password)
        try:
            meta = self._decode_meta(await r.hgetall(_META_KEY))
            if meta is None:
                # Shared copy missing (Redis flushed/restarted without
                # persistence): fall back to any local copy and rebuild.
                self._kick_rebuild()
                return self.check_password(password)
            pipe = r.pipeline(transaction=False)
            for pos in bloom_positions(password, meta["bit_count"], meta["num_hashes"]):
                pipe.getbit(_BITS_KEY, _redis_bit(pos))
            return all(await pipe.execute())
        except Exception as e:
            logger.warning(f"Shared Bloom check failed, using local copy: {e}")
            return self.check_password(password)

    def _kick_rebuild(self) -> None:
        try:
            from database import AsyncSessionLocal
            loop = asyncio.get_running_loop()
            loop.create_task(self.load_from_db(AsyncSessionLocal))
        except RuntimeError:
            pass

    async def status(self) -> Tuple[bool, bool, int]:
        """(loaded, loading, count) — cluster-wide in shared mode."""
        from utils.cluster import async_redis
        r = await async_redis()
        if r is None:
            return self._loaded, self._loading, self._count
        try:
            meta = self._decode_meta(await r.hgetall(_META_KEY))
            loading = bool(await r.exists(_LOADING_KEY))
            if meta is None:
                return False, loading, 0
            return True, loading, meta.get("count", 0)
        except Exception:
            return self._loaded, self._loading, self._count

    def begin_loading(self) -> bool:
        """Take the build lock. False if another worker is already building."""
        r = self._shared_sync()
        if r is None:
            if self._loading:
                return False
            self._loading = True
            return True
        try:
            if not r.set(_LOADING_KEY, b"1", nx=True, ex=_LOADING_TTL):
                return False
        except Exception:
            pass
        self._loading = True
        return True

    def end_loading(self) -> None:
        self._loading = False
        r = self._shared_sync()
        if r is not None:
            try:
                r.delete(_LOADING_KEY)
            except Exception:
                pass

    def install(self, bloom: BloomFilter, count: int) -> None:
        """Make ``bloom`` the live filter (shared copy, or local copy)."""
        r = self._shared_sync()
        if r is not None:
            try:
                pipe = r.pipeline(transaction=True)
                pipe.set(_BITS_KEY, bytes(bloom.bit_array))
                pipe.delete(_META_KEY)
                pipe.hset(_META_KEY, mapping={
                    "bit_count": bloom.bit_count, "num_hashes": bloom.num_hashes, "count": count,
                })
                pipe.execute()
                self._bloom = None  # no per-worker copy in shared mode
                self._count = count
                self._loaded = True
                return
            except Exception as e:
                logger.warning(f"Publishing shared Bloom filter failed, keeping it local: {e}")
        self._bloom = bloom
        self._count = count
        self._loaded = True

    def add_many(self, passwords: list) -> None:
        """Add passwords to the live filter (wordlist import)."""
        passwords = [p for p in passwords if p]
        if not passwords:
            return
        r = self._shared_sync()
        if r is not None:
            try:
                meta = self._decode_meta(r.hgetall(_META_KEY))
                if meta is not None:
                    pipe = r.pipeline(transaction=False)
                    for pw in passwords:
                        for pos in bloom_positions(pw, meta["bit_count"], meta["num_hashes"]):
                            pipe.setbit(_BITS_KEY, _redis_bit(pos), 1)
                    pipe.hincrby(_META_KEY, "count", len(passwords))
                    pipe.execute()
                    self._count = meta.get("count", 0) + len(passwords)
                    return
            except Exception as e:
                logger.warning(f"Shared Bloom add failed, adding locally: {e}")
        self.rebuild_sync_add(passwords)

    async def load_from_db(self, db_session_factory):
        """Startup load. In shared mode only one worker builds, and only when
        Redis doesn't already hold a filter."""
        from utils.cluster import async_redis
        r = await async_redis()
        if r is not None:
            try:
                meta = self._decode_meta(await r.hgetall(_META_KEY))
                if meta is not None:
                    self._loaded, self._count = True, meta.get("count", 0)
                    logger.info("Bloom filter: using shared copy (%s entries)", self._count)
                    return
            except Exception:
                pass
        if not await asyncio.to_thread(self.begin_loading):
            return

        logger.info("Loading Bloom filter from database...")
        try:
            from sqlalchemy import select, func
            from models.wordlist import WordlistEntry

            async with db_session_factory() as session:
                total = (await session.execute(select(func.count(WordlistEntry.id)))).scalar() or 0
                bloom = BloomFilter(capacity=max(total, 1000))
                loaded = 0
                if total:
                    # Stream instead of OFFSET pages: OFFSET re-scans every
                    # earlier row, quadratic over a 14M-row table.
                    stream = await session.stream_scalars(
                        select(WordlistEntry.password).execution_options(yield_per=50000)
                    )
                    async for pw in stream:
                        if pw:
                            bloom.add(pw)
                            loaded += 1
                            if loaded % 1_000_000 == 0:
                                logger.info(f"Bloom filter: loaded {loaded}/{total} entries...")
            await asyncio.to_thread(self.install, bloom, loaded)
            logger.info(f"Bloom filter ready with {loaded} entries (~{bloom.byte_count // 1024 // 1024}MB)")
        except Exception as e:
            logger.error(f"Failed to load Bloom filter: {e}")
            if self._bloom is None and not self._loaded:
                self._bloom = BloomFilter(capacity=1000)
                self._loaded = True
        finally:
            await asyncio.to_thread(self.end_loading)

    def rebuild_sync_add(self, passwords: list):
        """Local-mode add (also the fallback for ``add_many``)."""
        if self._bloom is None:
            self._bloom = BloomFilter(capacity=max(len(passwords), 20_000_000))
            self._loaded = True

        for pw in passwords:
            if pw:
                self._bloom.add(pw)
                self._count += 1


# Global singleton
bloom_service = BloomFilterService()
