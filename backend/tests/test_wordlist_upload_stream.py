"""Wordlist uploads are copied to disk off the event loop with a size cap."""

from __future__ import annotations

import io
import os


def test_copy_capped_writes_and_enforces_cap(tmp_path):
    from routers.wordlist import _copy_capped
    dest = tmp_path / "w.txt"
    _copy_capped(io.BytesIO(b"a\nb\n" * 1000), str(dest), 10_000, chunk=7)
    assert dest.read_bytes() == b"a\nb\n" * 1000
    big = tmp_path / "big.txt"
    try:
        _copy_capped(io.BytesIO(b"x" * 101), str(big), 100, chunk=10)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
    assert not os.path.exists(big)


async def test_upload_over_cap_is_413(client, make_user, authenticate_as, monkeypatch):
    import routers.wordlist as wl
    monkeypatch.setattr(wl, "MAX_WORDLIST_BYTES", 10)
    authenticate_as(await make_user(role="admin"))
    r = await client.post("/wordlist/upload", files={"file": ("w.txt", b"password123\n" * 5, "text/plain")})
    assert r.status_code == 413, r.text
