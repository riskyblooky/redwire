"""``_stream_spooled_zip`` regressions.

GHSA-q8q6-22jx-7rjj follow-up. The JSON_ZIP / JSON_LAYOUT_ZIP report
exports used to build the archive into ``io.BytesIO()`` then return
``Response(content=zip_buffer.getvalue(), ...)`` — two full copies of
the archive in memory at peak. The refactor builds into a
``SpooledTemporaryFile`` (rolls to disk above ``_ZIP_SPOOL_THRESHOLD``)
and streams chunks via ``StreamingResponse``, so memory pressure is
bounded regardless of evidence aggregate size.

These tests pin the streaming generator: it yields chunks of the
expected size, the archive is consumable end-to-end (a real zipfile
on the other side reads back the same content), and the underlying
spooled file gets closed when the iterator exhausts.
"""

from __future__ import annotations

import io
import tempfile
import zipfile

from routers.reports import (
    _ZIP_STREAM_CHUNK,
    _ZIP_SPOOL_THRESHOLD,
    _stream_spooled_zip,
)


def _build_spooled_zip(entries: dict[str, bytes]) -> tempfile.SpooledTemporaryFile:
    """Build a ZIP with the given {arcname: bytes} into a spooled file."""
    spooled = tempfile.SpooledTemporaryFile(
        max_size=_ZIP_SPOOL_THRESHOLD, mode="w+b"
    )
    with zipfile.ZipFile(spooled, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, payload in entries.items():
            zf.writestr(name, payload)
    spooled.seek(0)
    return spooled


def test_stream_yields_chunks_no_larger_than_chunk_size():
    spooled = _build_spooled_zip({
        "engagement_export.json": b'{"engagement_id": "x"}',
        "attachments/findings/f1/screenshot.png": b"X" * 200_000,
    })
    chunks = list(_stream_spooled_zip(spooled))
    assert all(len(c) <= _ZIP_STREAM_CHUNK for c in chunks)
    assert sum(len(c) for c in chunks) > 0


def test_streamed_archive_is_readable_end_to_end():
    """The streamed bytes reassemble into a valid ZIP whose contents
    match what we wrote in. Catches any regression where the stream
    chunks misalign or the spooled file isn't seek(0)'d."""
    payload_json = b'{"hello": "world"}'
    payload_png = b"\x89PNG" + b"X" * 100_000
    spooled = _build_spooled_zip({
        "engagement_export.json": payload_json,
        "attachments/findings/f1/shot.png": payload_png,
    })

    reassembled = b"".join(_stream_spooled_zip(spooled))

    with zipfile.ZipFile(io.BytesIO(reassembled)) as zf:
        assert zf.read("engagement_export.json") == payload_json
        assert zf.read("attachments/findings/f1/shot.png") == payload_png


def test_stream_closes_spooled_when_iterator_exhausts():
    """``SpooledTemporaryFile.close()`` deletes the on-disk backing
    file. The generator's ``finally`` must run that close so we don't
    leak tempfiles even when the response completes normally."""
    spooled = _build_spooled_zip({"x.json": b"{}"})

    # Drain the generator.
    list(_stream_spooled_zip(spooled))

    # After exhaustion, the file should be closed; .read() on a closed
    # spooled tempfile raises ValueError.
    import pytest
    with pytest.raises(ValueError):
        spooled.read(1)


def test_stream_closes_spooled_on_client_abort():
    """Client-abort case: the generator is garbage-collected mid-stream.
    Python's generator protocol calls ``__del__`` → ``close()`` on the
    generator, which runs the ``finally`` block, which closes the file.
    Pin this so a future refactor doesn't accidentally lose the cleanup
    path."""
    spooled = _build_spooled_zip({"x.json": b"X" * 500_000})

    gen = _stream_spooled_zip(spooled)
    # Pull one chunk then drop the generator without exhausting.
    first = next(gen)
    assert first  # got something
    gen.close()  # explicit close mirrors GC-triggered close

    import pytest
    with pytest.raises(ValueError):
        spooled.read(1)


def test_small_archive_stays_in_memory():
    """``SpooledTemporaryFile`` doesn't roll over to disk under its
    ``max_size`` threshold. This is the fast-path for the common
    small-export case — pin that the spool threshold is set high
    enough for a typical engagement export to stay in RAM."""
    spooled = _build_spooled_zip({"x.json": b"X" * 1024})
    # Internal _file is BytesIO before rollover; SpooledTemporaryFile
    # exposes ``_rolled`` for inspection.
    assert spooled._rolled is False
    # Drain so the test doesn't leave the file open.
    list(_stream_spooled_zip(spooled))
