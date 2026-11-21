"""EXIF read and strip on image evidence, against a fake object store."""

from __future__ import annotations

import io
import uuid

import pytest
from PIL import Image

from tests.test_authz_boundaries import _make_engagement, _make_finding


def _jpeg_with_exif() -> bytes:
    img = Image.new("RGB", (8, 8), "red")
    exif = Image.Exif()
    exif[0x010F] = "AcmeCam"              # Make
    exif[0x0110] = "Model 7"              # Model
    exif[0x0132] = "2026:01:02 03:04:05"  # DateTime
    out = io.BytesIO()
    img.save(out, format="JPEG", exif=exif)
    return out.getvalue()


@pytest.fixture
def store(monkeypatch):
    """In-memory stand-in for storage_service's read and write."""
    from utils.storage import storage_service

    objects: dict[str, bytes] = {}

    async def download_file(name):
        return objects[name]

    async def upload_file(content, name, content_type=None):
        objects[name] = content
        return name

    monkeypatch.setattr(storage_service, "download_file", download_file)
    monkeypatch.setattr(storage_service, "upload_file", upload_file)
    return objects


async def _image_evidence(db, store, user):
    from models.evidence import Evidence

    eng = await _make_engagement(db)
    finding = await _make_finding(db, eng, created_by=user.id)
    data = _jpeg_with_exif()
    name = f"evidence/{uuid.uuid4()}.jpg"
    store[name] = data
    ev = Evidence(
        id=str(uuid.uuid4()), finding_id=finding.id, engagement_id=eng.id,
        filename=name, original_filename="shot.jpg", file_path=name,
        file_size=len(data), mime_type="image/jpeg", created_by=user.id,
    )
    db.add(ev)
    await db.flush()
    return ev


async def test_exif_is_read_from_storage(client, db_session, make_user, authenticate_as, store):
    admin = await make_user(role="admin")
    ev = await _image_evidence(db_session, store, admin)
    authenticate_as(admin)

    r = await client.get(f"/evidence/{ev.id}/exif")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["has_exif"] is True
    assert body["exif"]["Make"] == "AcmeCam"
    assert body["exif"]["Model"] == "Model 7"


async def test_strip_exif_rewrites_the_object(client, db_session, make_user, authenticate_as, store):
    admin = await make_user(role="admin")
    ev = await _image_evidence(db_session, store, admin)
    authenticate_as(admin)

    r = await client.post(f"/evidence/{ev.id}/strip-exif")

    assert r.status_code == 200, r.text
    assert r.json()["date_taken"] == "2026:01:02 03:04:05"
    stripped = Image.open(io.BytesIO(store[ev.filename]))
    assert not stripped.getexif()
    assert r.json()["new_file_size"] == len(store[ev.filename])

    after = (await client.get(f"/evidence/{ev.id}/exif")).json()
    assert after == {"exif": {}, "has_exif": False}


async def test_storage_failure_is_a_clean_500(client, db_session, make_user, authenticate_as, store):
    admin = await make_user(role="admin")
    ev = await _image_evidence(db_session, store, admin)
    del store[ev.filename]
    authenticate_as(admin)

    r = await client.get(f"/evidence/{ev.id}/exif")

    assert r.status_code == 500
    assert r.json()["detail"] == "Failed to read file"
