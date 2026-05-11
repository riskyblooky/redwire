from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Boolean, Enum as SQLEnum
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime
import uuid
import enum

class ResourceType(str, enum.Enum):
    ENGAGEMENT = "engagement"
    FINDING = "finding"
    ASSET = "asset"
    TESTCASE = "testcase"
    EVIDENCE = "evidence"
    COMMENT = "comment"
    VAULT = "vault"
    THREAD = "thread"
    TEMPLATE = "template"
    NOTE = "note"
    CLEANUP_ARTIFACT = "cleanup_artifact"
    FINDING_REMEDIATION = "finding_remediation"

class Thread(Base):
    __tablename__ = "threads"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    engagement_id = Column(String, ForeignKey("engagements.id"), nullable=False)
    resource_type = Column(String(50), nullable=False)  # Changed from Enum to String
    resource_id = Column(String, nullable=True, index=True) # ID of specific finding/asset/testcase
    title = Column(String(255), nullable=False)
    created_by = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_resolved = Column(Boolean, default=False)
    
    # Relationships
    engagement = relationship("Engagement", back_populates="threads", foreign_keys="Thread.engagement_id")
    author = relationship("User", foreign_keys="Thread.created_by")
    comments = relationship("Comment", back_populates="thread", cascade="all, delete-orphan")

class Comment(Base):
    __tablename__ = "comments"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    thread_id = Column(String, ForeignKey("threads.id"), nullable=False)
    content = Column(Text, nullable=False)
    created_by = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Resolvable features (for peer review)
    is_resolvable = Column(Boolean, default=False)
    is_resolved = Column(Boolean, default=False)
    resolved_by = Column(String, ForeignKey("users.id"), nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    
    # Relationships
    thread = relationship("Thread", back_populates="comments")
    author = relationship("User", foreign_keys="Comment.created_by")
    resolver = relationship("User", foreign_keys="Comment.resolved_by")

class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    engagement_id = Column(String, ForeignKey("engagements.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    action = Column(String(100), nullable=False) # e.g., "created", "updated", "deleted", "resolved"
    resource_type = Column(String(50), nullable=False)  # Changed from Enum to String
    resource_id = Column(String, nullable=False)
    resource_name = Column(String(255), nullable=True) # Friendly name of the resource
    details = Column(Text, nullable=True) # JSON or descriptive string of changes
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    engagement = relationship("Engagement", back_populates="activity_logs", foreign_keys="ActivityLog.engagement_id")
    user = relationship("User", foreign_keys="ActivityLog.user_id")
