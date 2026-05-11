from sqlalchemy import Column, String, DateTime, Boolean, Enum as SQLEnum, ForeignKey, JSON
from sqlalchemy.orm import relationship
from database import Base
from models.associations import EngagementAssignment
from models.group import user_groups

from datetime import datetime
import uuid
import enum

class UserRole(str, enum.Enum):
    ADMIN = "admin"
    READ_ONLY_ADMIN = "read_only_admin"
    TEAM_LEAD = "team_lead"
    OPERATOR = "operator"
    READ_ONLY = "read_only"

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255))
    profile_photo = Column(String(255), nullable=True)
    role = Column(SQLEnum(UserRole), nullable=False, default=UserRole.OPERATOR)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_login = Column(DateTime)
    last_active = Column(DateTime, default=datetime.utcnow)
    must_change_password = Column(Boolean, default=False, nullable=False, server_default="false")
    registration_code_id = Column(String, ForeignKey("registration_codes.id", ondelete="SET NULL"), nullable=True)

    # Two-Factor Authentication
    totp_secret = Column(String(256), nullable=True)  # Fernet-encrypted
    totp_enabled = Column(Boolean, default=False, nullable=False)
    totp_verified_at = Column(DateTime, nullable=True)

    # Authentication provider: 'local', 'ldap', or 'saml'
    auth_provider = Column(String(16), default="local", nullable=False, server_default="local")

    # Dashboard customization
    dashboard_layout = Column(JSON, nullable=True)  # User's widget layout

    # Accent color: one of 'purple' (default), 'crimson', 'teal', 'emerald', 'amber'
    theme_preference = Column(String(32), nullable=False, default="purple", server_default="purple")

    # Surface palette: one of 'aurora' (default), 'operator', 'half-dark', 'light'
    theme_palette = Column(String(32), nullable=False, default="aurora", server_default="aurora")

    # Optional custom accent — hex like "#a855f7". Only applied when
    # theme_preference == "custom".
    theme_accent_custom = Column(String(7), nullable=True)

    # Relationships
    findings = relationship("Finding", back_populates="created_by_user", foreign_keys="Finding.created_by")
    created_engagements = relationship("Engagement", back_populates="created_by_user", foreign_keys="Engagement.created_by")
    assignment_details = relationship("EngagementAssignment", back_populates="user", cascade="all, delete-orphan")
    assigned_engagements = relationship(
        "Engagement", 
        secondary="engagement_assignments", 
        primaryjoin="User.id == EngagementAssignment.user_id",
        secondaryjoin="EngagementAssignment.engagement_id == Engagement.id",
        back_populates="assigned_users", 
        viewonly=True
    )
    groups = relationship("Group", secondary=user_groups, back_populates="users")
    calendar_events = relationship("CalendarEvent", back_populates="created_by_user", foreign_keys="CalendarEvent.created_by")
    registration_code = relationship("RegistrationCode", foreign_keys=[registration_code_id])
    client_access = relationship("ClientUserAccess", foreign_keys="ClientUserAccess.user_id", cascade="all, delete-orphan")
    skills = relationship("UserSkill", back_populates="user", cascade="all, delete-orphan")

