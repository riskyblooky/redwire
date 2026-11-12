from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from pydantic import BaseModel, Field
from typing import Optional
import threading
import logging
import os
import re

from database import get_db, AsyncSessionLocal
from models.user import User, UserRole
from models.wordlist import WordlistEntry, WordlistMeta, WordlistStatus
from auth.dependencies import get_current_user
from utils.hash_utils import (
    compute_all_hashes,
    compute_ntlm,
    identify_hash_type,
    bloom_service,
    bloom_capacity_for,
)
from utils.paths import ensure_within

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/wordlist", tags=["wordlist"])

UPLOAD_DIR = "uploads/wordlists"
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ── Request/Response Schemas ──

class CheckPasswordRequest(BaseModel):
    # Wordlist passwords are real-world strings; 256 covers the long tail.
    password: str = Field(..., max_length=256)

class CheckPasswordResponse(BaseModel):
    found: bool

class LookupHashRequest(BaseModel):
    # Longest practical hash (e.g. krb5tgs) tops out around 1 KB; 4 KB is
    # safe headroom while still blocking the multi-MB-DoS path.
    hash: str = Field(..., max_length=4096)

class LookupHashResponse(BaseModel):
    found: bool
    password: Optional[str] = None
    hash_type: Optional[str] = None
    note: Optional[str] = None

class WordlistStatusItem(BaseModel):
    id: str
    filename: str
    entry_count: int
    status: str
    error_message: Optional[str] = None
    uploaded_by: Optional[str] = None
    created_at: str

class WordlistStatusResponse(BaseModel):
    bloom_loaded: bool
    bloom_loading: bool
    bloom_count: int
    wordlists: list[WordlistStatusItem]


# ── Endpoints ──
#
# Wordlist check / hash-lookup / status are intentionally open to ANY
# authenticated operator (no dedicated permission). This is a core red-team
# operator capability, not an admin privilege: cracking needs a hash the caller
# already has access to (no escalation), and the same wordlist bloom filter
# already runs for every user on password change. In a self-hosted platform,
# "authenticated" is the trust boundary. A WORDLIST_USE permission granted to
# the Default group would be pure ceremony. Wordlist *upload/delete* (managing
# the shared dataset) stays role-restricted below. See project_rbac_three_tier.

@router.post("/check-password", response_model=CheckPasswordResponse)
async def check_password(
    req: CheckPasswordRequest,
    current_user: User = Depends(get_current_user),
):
    """Check if a plaintext password is in any uploaded wordlist (uses Bloom filter)."""
    found = await bloom_service.check_password_async(req.password)
    return CheckPasswordResponse(found=found)


@router.post("/lookup-hash", response_model=LookupHashResponse)
async def lookup_hash(
    req: LookupHashRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Look up a hash to find the plaintext password. Works for NTLM, MD5, SHA-1."""
    hash_type = identify_hash_type(req.hash)

    if hash_type in ("bcrypt", "krb5tgs"):
        return LookupHashResponse(
            found=False,
            note=f"{hash_type} is a salted hash format — cannot reverse-lookup. "
                 f"Use 'check-password' with the plaintext instead.",
        )

    if hash_type is None:
        return LookupHashResponse(found=False, note="Unrecognized hash format.")

    h = req.hash.strip().lower()

    # Query the database for matching hash
    if hash_type == "md5_or_ntlm":
        # 32-char hex could be MD5 or NTLM — check both
        result = await db.execute(
            select(WordlistEntry.password)
            .where((WordlistEntry.md5 == h) | (WordlistEntry.ntlm == h))
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row:
            # Determine which one matched
            from utils.hash_utils import compute_md5, compute_ntlm
            if compute_md5(row) == h:
                return LookupHashResponse(found=True, password=row, hash_type="md5")
            elif compute_ntlm(row) == h:
                return LookupHashResponse(found=True, password=row, hash_type="ntlm")
            return LookupHashResponse(found=True, password=row, hash_type="md5_or_ntlm")
    elif hash_type == "sha1":
        result = await db.execute(
            select(WordlistEntry.password)
            .where(WordlistEntry.sha1 == h)
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row:
            return LookupHashResponse(found=True, password=row, hash_type="sha1")

    return LookupHashResponse(found=False)


@router.get("/status", response_model=WordlistStatusResponse)
async def get_wordlist_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get status of all uploaded wordlists and Bloom filter."""
    result = await db.execute(
        select(WordlistMeta).order_by(WordlistMeta.created_at.desc())
    )
    metas = result.scalars().all()

    items = []
    for m in metas:
        items.append(WordlistStatusItem(
            id=m.id,
            filename=m.filename,
            entry_count=m.entry_count,
            status=m.status,
            error_message=m.error_message,
            uploaded_by=m.uploaded_by,
            created_at=m.created_at.isoformat() if m.created_at else "",
        ))

    bloom_loaded, bloom_loading, bloom_count = await bloom_service.status()
    return WordlistStatusResponse(
        bloom_loaded=bloom_loaded,
        bloom_loading=bloom_loading,
        bloom_count=bloom_count,
        wordlists=items,
    )


@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_wordlist(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload a wordlist file. Processing happens in the background."""
    # Admin only
    if current_user.role not in [UserRole.ADMIN, UserRole.TEAM_LEAD]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can upload wordlists.",
        )

    # Allow-list sanitiser — keep alphanumerics, dot, underscore, hyphen.
    # Strip leading dots so a filename like ".bashrc" cannot land as a
    # dotfile on disk. Empty result falls back to "wordlist.txt".
    raw_name = file.filename or "wordlist.txt"
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", raw_name).lstrip(".") or "wordlist.txt"
    file_path = os.path.join(UPLOAD_DIR, f"{os.urandom(8).hex()}_{safe_name}")
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    # Create metadata record
    meta = WordlistMeta(
        filename=safe_name,
        status=WordlistStatus.PROCESSING.value,
        uploaded_by=current_user.id,
    )
    db.add(meta)
    await db.commit()
    await db.refresh(meta)

    meta_id = meta.id

    # Process in background thread
    thread = threading.Thread(
        target=_process_wordlist_sync,
        args=(file_path, meta_id),
        daemon=True,
    )
    thread.start()

    return {"id": meta_id, "status": "PROCESSING", "filename": safe_name}


@router.delete("/{wordlist_id}", status_code=status.HTTP_200_OK)
async def delete_wordlist(
    wordlist_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a wordlist and all its entries. Rebuilds the Bloom filter."""
    if current_user.role not in [UserRole.ADMIN, UserRole.TEAM_LEAD]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can delete wordlists.",
        )

    result = await db.execute(
        select(WordlistMeta).where(WordlistMeta.id == wordlist_id)
    )
    meta = result.scalar_one_or_none()
    if not meta:
        raise HTTPException(status_code=404, detail="Wordlist not found.")

    # Delete entries
    await db.execute(
        delete(WordlistEntry).where(WordlistEntry.source == wordlist_id)
    )
    await db.delete(meta)
    await db.commit()

    # Rebuild Bloom filter in background
    thread = threading.Thread(
        target=_rebuild_bloom_sync,
        daemon=True,
    )
    thread.start()

    return {"detail": "Wordlist deleted. Bloom filter is rebuilding."}


# ── Background Processing ──

def _get_sync_database_url() -> str:
    """Convert async DB URL to sync for background threads."""
    url = os.environ.get("DATABASE_URL", "postgresql+asyncpg://redwire:changeme@localhost:5432/redwire")
    # Replace asyncpg driver with psycopg2
    return url.replace("postgresql+asyncpg://", "postgresql://").replace("asyncpg://", "postgresql://")


def _process_wordlist_sync(file_path: str, meta_id: str):
    """Background thread: parse wordlist, compute hashes, bulk insert, update Bloom filter."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    sync_url = _get_sync_database_url()
    sync_engine = create_engine(sync_url, pool_pre_ping=True)

    batch_size = 10000
    total_count = 0

    try:
        with Session(sync_engine) as session:
            batch = []
            batch_pw = []

            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    password = line.rstrip("\n\r")
                    if not password:
                        continue

                    hashes = compute_all_hashes(password)
                    batch.append(WordlistEntry(
                        password=password,
                        ntlm=hashes["ntlm"],
                        md5=hashes["md5"],
                        sha1=hashes["sha1"],
                        source=meta_id,
                    ))

                    batch_pw.append(password)
                    total_count += 1

                    if len(batch) >= batch_size:
                        session.add_all(batch)
                        session.commit()
                        bloom_service.add_many(batch_pw)
                        batch_pw = []
                        logger.info(f"Wordlist {meta_id}: inserted {total_count} entries...")
                        batch = []

            # Insert remaining batch
            if batch:
                session.add_all(batch)
                session.commit()
                bloom_service.add_many(batch_pw)

            # Update metadata
            meta = session.query(WordlistMeta).filter(WordlistMeta.id == meta_id).first()
            if meta:
                meta.entry_count = total_count
                meta.status = WordlistStatus.READY.value
                session.commit()

            logger.info(f"Wordlist {meta_id}: done — {total_count} entries imported.")

        # The import outgrew the live filter: rebuild it at the new size
        # (still in this background thread), or check-password would report
        # nearly every password as found.
        if bloom_service.over_capacity():
            logger.info(f"Wordlist {meta_id}: Bloom filter over capacity, rebuilding")
            _rebuild_bloom_sync()

    except Exception as e:
        logger.error(f"Wordlist {meta_id} processing failed: {e}")
        try:
            with Session(sync_engine) as session:
                meta = session.query(WordlistMeta).filter(WordlistMeta.id == meta_id).first()
                if meta:
                    meta.status = WordlistStatus.FAILED.value
                    meta.error_message = str(e)[:500]
                    session.commit()
        except Exception:
            pass
    finally:
        if ensure_within(file_path, UPLOAD_DIR):
            try:
                os.remove(file_path)
            except Exception:
                pass
        else:
            logger.warning(
                "Refusing to remove wordlist path outside upload dir: %s",
                file_path,
            )
        sync_engine.dispose()


def _rebuild_bloom_sync():
    """Background thread: rebuild the Bloom filter from scratch using sync DB
    and install it (shared Redis copy when available, else this worker's)."""
    import time
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from utils.hash_utils import BloomFilter, bloom_capacity_for

    # Another worker may be mid-build from rows read before this change;
    # wait for it, then rebuild so the deletion is reflected.
    deadline = time.monotonic() + 600
    while not bloom_service.begin_loading():
        if time.monotonic() > deadline:
            logger.error("Bloom rebuild skipped: build lock held for over 10 minutes")
            return
        time.sleep(5)

    sync_url = _get_sync_database_url()
    sync_engine = create_engine(sync_url, pool_pre_ping=True)
    try:
        with Session(sync_engine) as session:
            total = session.query(func.count(WordlistEntry.id)).scalar() or 0
            bloom = BloomFilter(capacity=bloom_capacity_for(total))
            loaded = 0
            for (pw,) in session.query(WordlistEntry.password).yield_per(50000):
                if pw:
                    bloom.add(pw)
                    loaded += 1
        bloom_service.install(bloom, loaded)
        logger.info(f"Bloom filter rebuilt with {loaded} entries")
    except Exception as e:
        logger.error(f"Failed to rebuild Bloom filter: {e}")
    finally:
        bloom_service.end_loading()
        sync_engine.dispose()


# Arbitrary, fixed: one backfill at a time across backend workers.
_NTLM_BACKFILL_LOCK_KEY = 0x4E544C4D  # "NTLM"


def backfill_missing_ntlm_sync(batch_size: int = 5000) -> int:
    """Fill in ``wordlist_entries.ntlm`` where it is empty.

    Until hash_utils gained a pure-Python MD4, every entry imported on an
    OpenSSL 3 image (the backend image) was stored with ntlm = '' — NTLM
    lookups never matched. Runs at startup in a background thread; resumable
    (it only ever selects still-empty rows) and single-flight across workers
    via a Postgres advisory lock. Returns the number of rows filled.
    """
    from sqlalchemy import create_engine, text

    engine = create_engine(_get_sync_database_url(), pool_pre_ping=True)
    filled = 0
    try:
        with engine.connect() as conn:
            if not conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _NTLM_BACKFILL_LOCK_KEY}).scalar():
                return 0
            try:
                last_id = 0
                while True:
                    rows = conn.execute(text(
                        "SELECT id, password FROM wordlist_entries "
                        "WHERE (ntlm IS NULL OR ntlm = '') AND id > :last "
                        "ORDER BY id LIMIT :n"), {"last": last_id, "n": batch_size}).all()
                    if not rows:
                        break
                    ids = [r[0] for r in rows]
                    hashes = [compute_ntlm(r[1] or "") for r in rows]
                    conn.execute(text(
                        "UPDATE wordlist_entries AS w SET ntlm = v.ntlm "
                        "FROM unnest(CAST(:ids AS integer[]), CAST(:hashes AS varchar[])) AS v(id, ntlm) "
                        "WHERE w.id = v.id"), {"ids": ids, "hashes": hashes})
                    conn.commit()
                    filled += len(rows)
                    last_id = ids[-1]
                    if filled % 500_000 < batch_size:
                        logger.info("NTLM backfill: %s entries filled", filled)
            finally:
                conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _NTLM_BACKFILL_LOCK_KEY})
                conn.commit()
        if filled:
            logger.info("NTLM backfill: done, %s entries filled", filled)
        return filled
    except Exception as e:
        logger.error(f"NTLM backfill failed after {filled} entries (will resume on next start): {e}")
        return filled
    finally:
        engine.dispose()

