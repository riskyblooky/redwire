from sqlalchemy import Column, String, DateTime, ForeignKey, Integer
from database import Base
from datetime import datetime
import uuid


class MarkdownImage(Base):
    """Image referenced inline by a markdown editor.

    Image bytes live in MinIO under `markdown/<id>.<ext>`. The DB row is
    the access-control gate: GET /markdown-images/{id} verifies the
    caller has view access to the engagement before streaming bytes.

    Lifecycle: rows are orphaned (not garbage-collected) when the markdown
    that referenced them is edited to remove the reference. That's
    acceptable; storage cost is small and a future cleanup job can scan
    referenced images vs. table rows.
    """
    __tablename__ = "markdown_images"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    storage_key = Column(String(512), nullable=False)
    engagement_id = Column(String, ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    content_type = Column(String(100), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    original_filename = Column(String(255), nullable=True)
