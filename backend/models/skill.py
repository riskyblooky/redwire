from sqlalchemy import Column, String, Text, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from database import Base
import uuid


class SkillCategory(Base):
    """A grouping for skills (e.g. Offensive, Defensive, Cloud)."""
    __tablename__ = "skill_categories"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False, unique=True)
    color = Column(String(7), nullable=True, default="#6366f1")
    sort_order = Column(Integer, nullable=False, default=0)

    skills = relationship("Skill", back_populates="category", cascade="all, delete-orphan", order_by="Skill.sort_order")


class Skill(Base):
    """An individual skill within a category."""
    __tablename__ = "skills"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    category_id = Column(String, ForeignKey("skill_categories.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)

    category = relationship("SkillCategory", back_populates="skills")

    __table_args__ = (
        UniqueConstraint('category_id', 'name', name='uq_skill_category_name'),
    )


class UserSkill(Base):
    """Maps a user to a skill with a proficiency level (0-3).

    `target_level`, when set, is the user's growth focus — the level they're
    working toward. Validation rule (enforced in router): target_level must
    equal level + 1, and a user can have at most 3 skills with target_level set.
    """
    __tablename__ = "user_skills"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    skill_id = Column(String, ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True)
    level = Column(Integer, nullable=False, default=0)  # 0=NONE, 1=BEGINNER, 2=INTERMEDIATE, 3=ADVANCED
    target_level = Column(Integer, nullable=True)

    user = relationship("User", back_populates="skills")
    skill = relationship("Skill")

    __table_args__ = (
        UniqueConstraint('user_id', 'skill_id', name='uq_user_skill'),
    )


class EngagementSkill(Base):
    """Maps an engagement to a required skill with a minimum level."""
    __tablename__ = "engagement_skills"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    engagement_id = Column(String, ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False, index=True)
    skill_id = Column(String, ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True)
    min_level = Column(Integer, nullable=False, default=1)  # minimum proficiency required

    engagement = relationship("Engagement", back_populates="required_skills")
    skill = relationship("Skill")

    __table_args__ = (
        UniqueConstraint('engagement_id', 'skill_id', name='uq_engagement_skill'),
    )
