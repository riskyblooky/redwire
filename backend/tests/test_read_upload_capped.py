"""``read_upload_capped`` streaming behaviour.

Pins the property the GHSA-h77m-pjqc-5cm3 follow-up for scanner imports
relies on: the helper bails the moment the running total crosses the
cap, *before* the full body is buffered. The previous pattern in
``imports.py`` read the entire body then checked size — a hostile
multi-GB upload allocated the whole thing before the 413 fired.

These tests use a fake ``UploadFile`` that hands out chunks one at a
time and counts how many chunks the helper consumed before raising.
A correct streaming implementation reads exactly enough chunks to
cross the cap and stops.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from utils.uploads import read_upload_capped


class _FakeUploadFile:
    """Mimics the slice of ``starlette.datastructures.UploadFile`` that
    ``read_upload_capped`` relies on."""

    def __init__(self, chunks: list[bytes], filename: str = "fake.bin"):
        self._chunks = list(chunks)
        self._next_idx = 0
        self.filename = filename
        self.reads_served = 0

    async def read(self, size: int = -1) -> bytes:
        # Count every call — including the trailing empty-read sentinel —
        # so tests can assert how many times the helper polled the stream.
        self.reads_served += 1
        if self._next_idx >= len(self._chunks):
            return b""
        chunk = self._chunks[self._next_idx]
        self._next_idx += 1
        # Helper passes chunk_size; we honour it by truncating, but a
        # real UploadFile would too. Tests below use chunks that already
        # fit within the requested size, so truncation never fires.
        return chunk[:size] if size > 0 else chunk


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_under_cap_returns_full_body():
    f = _FakeUploadFile([b"a" * 100, b"b" * 100])
    out = _run(read_upload_capped(f, max_bytes=1024, chunk_size=200))
    assert out == b"a" * 100 + b"b" * 100
    assert f.reads_served == 3  # two chunks + one empty-read sentinel


def test_at_exact_cap_returns_body():
    f = _FakeUploadFile([b"x" * 1024])
    out = _run(read_upload_capped(f, max_bytes=1024, chunk_size=2048))
    assert out == b"x" * 1024


def test_over_cap_raises_413_immediately_on_overflow_chunk():
    # The cap is 100 bytes. First chunk is 60 (running total 60, ok).
    # Second chunk is 60 (running total 120 > cap). Helper must raise
    # BEFORE asking for chunk 3 — that's the streaming bail.
    f = _FakeUploadFile([b"a" * 60, b"b" * 60, b"c" * 60])
    with pytest.raises(HTTPException) as exc:
        _run(read_upload_capped(f, max_bytes=100, chunk_size=60))
    assert exc.value.status_code == 413
    # Helper polled chunk 1 (60B, total 60) and chunk 2 (60B, total 120,
    # over cap) then raised. Anything past 2 reads means it kept draining.
    assert f.reads_served == 2, (
        f"Expected to bail after 2 reads; got {f.reads_served}. "
        "The helper must not keep reading once the cap is crossed."
    )


def test_attacker_supplied_unbounded_stream_does_not_drain():
    """The threat model: an attacker streams gigabytes. Cap is 1 KB.
    The helper should ask for one chunk past the cap then raise — not
    drain the entire stream."""
    # Lazy chunk producer: pretends to be infinite.
    big = [b"X" * 512 for _ in range(10_000)]
    f = _FakeUploadFile(big)
    with pytest.raises(HTTPException):
        _run(read_upload_capped(f, max_bytes=1024, chunk_size=512))
    # 1 KB cap, 512-byte chunks → reads at most 3 (2 fill, 3rd overflows).
    assert f.reads_served <= 3


def test_custom_detail_message_propagates():
    f = _FakeUploadFile([b"x" * 200])
    with pytest.raises(HTTPException) as exc:
        _run(read_upload_capped(f, max_bytes=100, chunk_size=200, detail="too big"))
    assert exc.value.detail == "too big"
