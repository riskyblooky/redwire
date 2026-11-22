"""strip-exif removes identifying metadata (GPS, camera) but keeps what its
docstring promises (the capture dates) plus Orientation, doesn't re-encode
a JPEG at a lower quality, and keeps every frame of an animated image."""

from __future__ import annotations

import io
import uuid

from PIL import ExifTags, Image, ImageChops

from models.evidence import Evidence
from utils.storage import storage_service


def _jpeg_with_exif() -> bytes:
    img = Image.new("RGB", (64, 48))
    for x in range(64):
        for y in range(48):
            img.putpixel((x, y), ((x * 4) % 256, (y * 5) % 256, (x * y) % 256))
    exif = Image.Exif()
    exif[0x0112] = 6                     # Orientation: rotate 90 CW
    exif[0x010F] = "AcmeCam"             # Make
    exif.get_ifd(ExifTags.IFD.Exif)[0x9003] = "2026:11:01 10:00:00"
    exif.get_ifd(ExifTags.IFD.GPSInfo)[2] = (51.0, 30.0, 0.0)
    out = io.BytesIO()
    img.save(out, "JPEG", quality=95, exif=exif.tobytes())
    return out.getvalue()


def _gif_3_frames() -> bytes:
    frames = [Image.new("RGB", (8, 8), c) for c in ((255, 0, 0), (0, 255, 0), (0, 0, 255))]
    out = io.BytesIO()
    frames[0].save(out, "GIF", save_all=True, append_images=frames[1:], duration=100, loop=0)
    return out.getvalue()


async def _strip(client, db_session, make_user, authenticate_as, data: bytes, mime: str) -> bytes:
    admin = await make_user(role="admin")
    key = f"test-exif/{uuid.uuid4()}"
    await storage_service.upload_file(data, key, mime)
    ev = Evidence(id=str(uuid.uuid4()), filename=key, original_filename="p", file_path=key,
                  file_size=len(data), mime_type=mime)
    db_session.add(ev)
    await db_session.flush()
    authenticate_as(admin)
    r = await client.post(f"/evidence/{ev.id}/strip-exif")
    assert r.status_code == 200, r.text
    return await storage_service.download_file(key)


async def test_jpeg_keeps_dates_orientation_and_quality(client, db_session, make_user, authenticate_as):
    src = _jpeg_with_exif()
    out = await _strip(client, db_session, make_user, authenticate_as, src, "image/jpeg")
    img = Image.open(io.BytesIO(out))
    exif = img.getexif()
    assert exif.get(0x0112) == 6
    assert exif.get_ifd(ExifTags.IFD.Exif).get(0x9003) == "2026:11:01 10:00:00"
    assert 0x010F not in exif and not exif.get_ifd(ExifTags.IFD.GPSInfo)
    # Same quantisation as the original (not a quality-75 re-encode).
    assert img.quantization == Image.open(io.BytesIO(src)).quantization


async def test_animated_gif_keeps_every_frame(client, db_session, make_user, authenticate_as):
    out = await _strip(client, db_session, make_user, authenticate_as, _gif_3_frames(), "image/gif")
    assert Image.open(io.BytesIO(out)).n_frames == 3
