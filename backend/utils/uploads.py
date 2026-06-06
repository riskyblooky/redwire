"""Bounded reads for `UploadFile` request bodies.

Centralized so every upload-accepting route applies the same byte cap
and reuses the same 413 shape. The chunked reader never lets more than
``max_bytes`` accumulate in memory — the moment the running total
exceeds the cap, the function raises and the partial buffer is dropped.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import HTTPException, UploadFile, status


logger = logging.getLogger(__name__)


async def read_upload_capped(
    file: UploadFile,
    max_bytes: int,
    *,
    detail: Optional[str] = None,
    chunk_size: int = 64 * 1024,
) -> bytes:
    """Read ``file`` into memory, refusing with 413 if the upload exceeds
    ``max_bytes``.

    The reader pulls ``chunk_size`` at a time and bails as soon as the
    accumulated total crosses the cap, so a hostile multi-GB upload
    can't drive worker memory past the limit even briefly. Bytes
    already buffered are released when the exception unwinds the stack.
    """
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            logger.warning(
                "Refused upload of %s: size > %d bytes (read %d before tripping the cap)",
                file.filename or "<unknown>", max_bytes, total,
            )
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=detail or (
                    f"Upload exceeds the {max_bytes}-byte size limit."
                ),
            )
        chunks.append(chunk)
    return b"".join(chunks)
