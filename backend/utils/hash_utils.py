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
        """Generate bit positions using double hashing with MD5+SHA1."""
        h1 = int(hashlib.md5(item.encode("utf-8", errors="replace")).hexdigest(), 16)
        h2 = int(hashlib.sha1(item.encode("utf-8", errors="replace")).hexdigest(), 16)
        positions = []
        for i in range(self.num_hashes):
            pos = (h1 + i * h2) % self.bit_count
            positions.append(pos)
        return positions

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


class BloomFilterService:
    """
    Singleton service managing the in-memory Bloom filter.
    Loaded from database on startup; rebuilt when wordlists change.
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
        """Check if a password is in the wordlist. Fast O(1) in-memory check."""
        if not self._loaded or self._bloom is None:
            return False
        return self._bloom.check(password)

    async def load_from_db(self, db_session_factory):
        """Load all passwords from the database into the Bloom filter."""
        if self._loading:
            return

        self._loading = True
        logger.info("Loading Bloom filter from database...")

        try:
            from sqlalchemy import select, func
            from models.wordlist import WordlistEntry

            async with db_session_factory() as session:
                # Get total count first
                count_result = await session.execute(
                    select(func.count(WordlistEntry.id))
                )
                total = count_result.scalar() or 0

                if total == 0:
                    self._bloom = BloomFilter(capacity=1000)
                    self._count = 0
                    self._loaded = True
                    self._loading = False
                    logger.info("No wordlist entries found. Bloom filter initialized empty.")
                    return

                # Build bloom filter
                bloom = BloomFilter(capacity=max(total, 1000))
                batch_size = 50000
                offset = 0
                loaded = 0

                while offset < total:
                    result = await session.execute(
                        select(WordlistEntry.password)
                        .offset(offset)
                        .limit(batch_size)
                    )
                    rows = result.scalars().all()
                    if not rows:
                        break
                    for pw in rows:
                        if pw:
                            bloom.add(pw)
                            loaded += 1
                    offset += batch_size
                    logger.info(f"Bloom filter: loaded {loaded}/{total} entries...")

                self._bloom = bloom
                self._count = loaded
                self._loaded = True
                logger.info(f"Bloom filter ready with {loaded} entries (~{bloom.byte_count // 1024 // 1024}MB)")

        except Exception as e:
            logger.error(f"Failed to load Bloom filter: {e}")
            self._bloom = BloomFilter(capacity=1000)
            self._loaded = True
        finally:
            self._loading = False

    def rebuild_sync_add(self, passwords: list):
        """Add a batch of passwords to the current Bloom filter (used during import)."""
        if self._bloom is None:
            self._bloom = BloomFilter(capacity=max(len(passwords), 20_000_000))
            self._loaded = True

        for pw in passwords:
            if pw:
                self._bloom.add(pw)
                self._count += 1


# Global singleton
bloom_service = BloomFilterService()
