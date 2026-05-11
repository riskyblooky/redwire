from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from pydantic import BaseModel
from typing import Optional
import threading
import logging
import os

from database import get_db, AsyncSessionLocal
from models.user import User, UserRole
from models.wordlist import WordlistEntry, WordlistMeta, WordlistStatus
from auth.dependencies import get_current_user
from utils.hash_utils import (
    compute_all_hashes,
    identify_hash_type,
    bloom_service,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/wordlist", tags=["wordlist"])

UPLOAD_DIR = "uploads/wordlists"
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ── Request/Response Schemas ──

class CheckPasswordRequest(BaseModel):
    password: str

class CheckPasswordResponse(BaseModel):
    found: bool

class LookupHashRequest(BaseModel):
    hash: str

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

@router.post("/check-password", response_model=CheckPasswordResponse)
async def check_password(
    req: CheckPasswordRequest,
    current_user: User = Depends(get_current_user),
):
    """Check if a plaintext password is in any uploaded wordlist (uses Bloom filter)."""
    found = bloom_service.check_password(req.password)
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

    return WordlistStatusResponse(
        bloom_loaded=bloom_service.is_loaded,
        bloom_loading=bloom_service._loading,
        bloom_count=bloom_service.count,
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
    if current_user.role not in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can upload wordlists.",
        )

    # Save file
    safe_name = file.filename.replace("/", "_").replace("\\", "_") if file.filename else "wordlist.txt"
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
    if current_user.role not in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]:
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

                    bloom_service.rebuild_sync_add([password])
                    total_count += 1

                    if len(batch) >= batch_size:
                        session.add_all(batch)
                        session.commit()
                        logger.info(f"Wordlist {meta_id}: inserted {total_count} entries...")
                        batch = []

            # Insert remaining batch
            if batch:
                session.add_all(batch)
                session.commit()

            # Update metadata
            meta = session.query(WordlistMeta).filter(WordlistMeta.id == meta_id).first()
            if meta:
                meta.entry_count = total_count
                meta.status = WordlistStatus.READY.value
                session.commit()

            logger.info(f"Wordlist {meta_id}: done — {total_count} entries imported.")

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
        try:
            os.remove(file_path)
        except Exception:
            pass
        sync_engine.dispose()


def _rebuild_bloom_sync():
    """Background thread: rebuild Bloom filter from scratch using sync DB."""
    from sqlalchemy import create_engine, select, func
    from sqlalchemy.orm import Session

    sync_url = _get_sync_database_url()
    sync_engine = create_engine(sync_url, pool_pre_ping=True)

    try:
        bloom_service._loading = True
        with Session(sync_engine) as session:
            total = session.query(func.count(WordlistEntry.id)).scalar() or 0

            if total == 0:
                from utils.hash_utils import BloomFilter
                bloom_service._bloom = BloomFilter(capacity=1000)
                bloom_service._count = 0
                bloom_service._loaded = True
                bloom_service._loading = False
                return

            from utils.hash_utils import BloomFilter
            bloom = BloomFilter(capacity=max(total, 1000))
            batch_size = 50000
            offset = 0
            loaded = 0

            while offset < total:
                rows = session.query(WordlistEntry.password).offset(offset).limit(batch_size).all()
                if not rows:
                    break
                for (pw,) in rows:
                    if pw:
                        bloom.add(pw)
                        loaded += 1
                offset += batch_size

            bloom_service._bloom = bloom
            bloom_service._count = loaded
            bloom_service._loaded = True
            logger.info(f"Bloom filter rebuilt with {loaded} entries")
    except Exception as e:
        logger.error(f"Failed to rebuild Bloom filter: {e}")
    finally:
        bloom_service._loading = False
        sync_engine.dispose()

