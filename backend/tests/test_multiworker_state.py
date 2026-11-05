"""Per-process state made safe for --workers > 1: Redis-backed rate-limit
storage, the cluster claim lock, and the shared wordlist Bloom filter."""

from __future__ import annotations

import uuid

import pytest

from utils import cluster, hash_utils
from utils.hash_utils import BloomFilter, bloom_service


def test_rate_limit_storage_precedence(monkeypatch):
    import rate_limit

    monkeypatch.setenv("REDIS_URL", "redis://r:6379/0")
    monkeypatch.delenv("RATE_LIMIT_STORAGE_URI", raising=False)
    assert rate_limit._storage_uri() == "redis://r:6379/0"
    monkeypatch.setenv("RATE_LIMIT_STORAGE_URI", "memory://")
    assert rate_limit._storage_uri() == "memory://"
    monkeypatch.delenv("RATE_LIMIT_STORAGE_URI")
    monkeypatch.delenv("REDIS_URL")
    assert rate_limit._storage_uri() == "memory://"


@pytest.fixture
def isolated_bloom(monkeypatch):
    """Point the service at throwaway Redis keys and restore its state."""
    tag = uuid.uuid4().hex[:8]
    monkeypatch.setattr(hash_utils, "_BITS_KEY", f"test:bloom:{tag}:bits")
    monkeypatch.setattr(hash_utils, "_META_KEY", f"test:bloom:{tag}:meta")
    monkeypatch.setattr(hash_utils, "_LOADING_KEY", f"test:bloom:{tag}:loading")
    saved = (bloom_service._bloom, bloom_service._loaded, bloom_service._loading, bloom_service._count)
    cluster.reset_clients()
    yield tag
    r = cluster.sync_redis()
    if r is not None:
        r.delete(hash_utils._BITS_KEY, hash_utils._META_KEY, hash_utils._LOADING_KEY)
    (bloom_service._bloom, bloom_service._loaded, bloom_service._loading, bloom_service._count) = saved
    cluster.reset_clients()


def _small_bloom(words):
    b = BloomFilter(capacity=1000)
    for w in words:
        b.add(w)
    return b


async def test_shared_bloom_install_check_add_status(isolated_bloom):
    if cluster.sync_redis() is None:
        pytest.skip("Redis not reachable")

    bloom_service.install(_small_bloom(["hunter2", "Summer2025!"]), 2)
    assert bloom_service._bloom is None  # no per-worker copy in shared mode

    assert await bloom_service.check_password_async("hunter2") is True
    assert await bloom_service.check_password_async("Summer2025!") is True
    assert await bloom_service.check_password_async("definitely-not-in-there-" + isolated_bloom) is False

    bloom_service.add_many(["Winter2026?"])
    assert await bloom_service.check_password_async("Winter2026?") is True
    assert await bloom_service.status() == (True, False, 3)

    # The build lock is exclusive across workers.
    assert bloom_service.begin_loading() is True
    assert bloom_service.begin_loading() is False
    assert (await bloom_service.status())[1] is True
    bloom_service.end_loading()
    assert bloom_service.begin_loading() is True
    bloom_service.end_loading()


async def test_local_bloom_when_redis_unavailable(isolated_bloom, monkeypatch):
    async def _none():
        return None
    monkeypatch.setattr(cluster, "sync_redis", lambda: None)
    monkeypatch.setattr(cluster, "async_redis", _none)

    bloom_service.install(_small_bloom(["letmein"]), 1)
    assert bloom_service._bloom is not None
    assert await bloom_service.check_password_async("letmein") is True
    assert await bloom_service.check_password_async("nope-" + isolated_bloom) is False
    bloom_service.add_many(["trustno1"])
    assert await bloom_service.check_password_async("trustno1") is True
    assert (await bloom_service.status())[0] is True


async def test_claim_is_exclusive():
    cluster.reset_clients()
    if await cluster.async_redis() is None:
        pytest.skip("Redis not reachable")
    name = f"test-{uuid.uuid4().hex[:8]}"
    try:
        assert await cluster.claim(name, 30) is True
        assert await cluster.claim(name, 30) is False
    finally:
        await (await cluster.async_redis()).delete(f"rw:claim:{name}")
        cluster.reset_clients()
