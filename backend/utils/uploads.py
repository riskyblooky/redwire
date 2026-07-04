"""Bounded reads for `UploadFile` request bodies.

Centralized so every upload-accepting route applies the same byte cap
and reuses the same 413 shape. The chunked reader never lets more than
``max_bytes`` accumulate in memory — the moment the running total
exceeds the cap, the function raises and the partial buffer is dropped.
"""
from __future__ import annotations

import logging
import mimetypes
import os
import unicodedata
from typing import Optional

from fastapi import HTTPException, UploadFile, status


logger = logging.getLogger(__name__)


def sanitize_original_filename(raw: Optional[str], fallback: str = "upload") -> str:
    """Normalize a user-supplied filename for safe storage in the DB
    ``original_filename`` column.

    GHSA-fwvp-qc8h-r5p4 follow-up. The GHSA fix sanitizes at every emit
    sink (JSON_ZIP export ZIP members + manifest attachment paths). This
    helper adds source-side scrubbing so the stored value can be trusted
    at rest and by any future emit path we haven't yet audited.

    Applied transforms:
      1. Strip directory components — a client that sends
         ``../../etc/passwd`` or ``C:\\Users\\x\\bad.exe`` reduces to
         the basename. Windows-style backslashes normalized first.
      2. NFKC Unicode normalization — collapses look-alike codepoints
         (e.g. fullwidth Latin) so the stored value matches what a
         reader will see rendered. Matches the username normalization
         from GHSA-2hrj-c2v3-8p2v.
      3. Drop control characters (categories Cc, Cf) so a filename
         can't smuggle a CR/LF/NUL into any downstream serializer.
      4. Fall back to ``fallback`` if the sanitized result is empty
         (all-control, all-slashes, missing extension only).

    Returns a plain str; never raises.
    """
    if not raw:
        return fallback
    # Windows path separators are legal characters on POSIX; normalize
    # BEFORE basename so both platforms strip the same way.
    normalized = raw.replace("\\", "/")
    basename = os.path.basename(normalized)
    if not basename:
        return fallback
    # NFKC folds fullwidth / compat forms into their canonical shape.
    basename = unicodedata.normalize("NFKC", basename)
    # Drop control chars (Cc = other/control, Cf = other/format including
    # zero-width joiner shenanigans). Keeps printable Unicode.
    cleaned = "".join(
        ch for ch in basename if unicodedata.category(ch) not in ("Cc", "Cf")
    ).strip()
    if not cleaned:
        return fallback
    # Cap at a reasonable filename length — some filesystems reject > 255.
    if len(cleaned) > 255:
        stem, dot, ext = cleaned.rpartition(".")
        if dot and len(ext) < 32:
            cleaned = stem[: 255 - len(ext) - 1] + "." + ext
        else:
            cleaned = cleaned[:255]
    return cleaned


# GHSA-h77m-pjqc-5cm3 follow-up: client-supplied ``Content-Type`` is the
# stored-XSS gadget the original advisory closed by forcing
# ``Content-Disposition: attachment`` on presigned URLs. That fix neutered
# the most common rendering paths, but image-shaped MIMEs (notably
# ``image/svg+xml``) still ride <img>/<embed>/<iframe> consumers that can
# bypass the disposition header. Two separate exposures remain even with
# the disposition fix in place:
#   1. The MIME the server stores is consumed by the frontend to decide
#      whether to inline-preview the file. An attacker-controlled MIME
#      lets them choose that branch.
#   2. SVG bytes can carry inline JS that fires when rendered as an image.
# This helper closes both: server picks the MIME from the *filename
# suffix* (never from the request header), and SVG is folded down to
# ``application/octet-stream`` so the frontend never picks the image
# branch for it. SVG is the only image type known to carry executable
# content, so the rest of the inline-preview UX (PNG / JPG / PDF
# screenshots) is preserved.
_UNSAFE_GUESSED_TYPES = frozenset({"image/svg+xml"})


def safe_content_type(filename: Optional[str]) -> str:
    """Derive a content type for storage and metadata that doesn't trust
    the client. ``filename`` is taken from ``UploadFile.filename``; the
    suffix is still client-supplied but it's a single discrete token, not
    an arbitrary header string, and the server has already sanitised the
    filename at the storage layer.

    Returns ``application/octet-stream`` for unknown extensions and for
    any extension that maps to a known XSS-carrying MIME (currently only
    ``image/svg+xml``).
    """
    if not filename:
        return "application/octet-stream"
    guessed, _ = mimetypes.guess_type(filename)
    if guessed is None or guessed in _UNSAFE_GUESSED_TYPES:
        return "application/octet-stream"
    return guessed


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
