from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func
from sqlalchemy.orm import selectinload
from database import get_db
from models.user import User, UserRole
from models.skill import SkillCategory, Skill, UserSkill, EngagementSkill
from schemas.skill import (
    SkillCategoryCreate, SkillCategoryUpdate, SkillCategoryResponse,
    SkillCreate, SkillUpdate, SkillResponse,
    UserSkillSet, UserSkillResponse,
    EngagementSkillSet, EngagementSkillResponse,
    EngagementFocusFit, FocusFitMatch, FocusFitSkill,
)

MAX_FOCUSES = 3
from auth.dependencies import get_current_user
from auth.permissions import require_global_permission
from models.permission import Permission
from typing import List

router = APIRouter(prefix="/skills", tags=["skills"])


# ══════════════════════════════════════════════════════════════════
#  SKILL CATEGORIES — Admin CRUD
# ══════════════════════════════════════════════════════════════════

@router.get("/categories", response_model=List[SkillCategoryResponse])
async def list_categories(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await require_global_permission(Permission.SKILL_VIEW, current_user, db)
    result = await db.execute(
        select(SkillCategory)
        .options(selectinload(SkillCategory.skills))
        .order_by(SkillCategory.sort_order, SkillCategory.name)
    )
    return result.scalars().all()


@router.post("/categories", response_model=SkillCategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(
    data: SkillCategoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await require_global_permission(Permission.SKILL_MANAGE_CATEGORIES, current_user, db)
    cat = SkillCategory(name=data.name, color=data.color, sort_order=data.sort_order or 0)
    db.add(cat)
    await db.commit()
    await db.refresh(cat, attribute_names=["skills"])
    return cat


@router.put("/categories/{cat_id}", response_model=SkillCategoryResponse)
async def update_category(
    cat_id: str,
    data: SkillCategoryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await require_global_permission(Permission.SKILL_MANAGE_CATEGORIES, current_user, db)
    result = await db.execute(
        select(SkillCategory).options(selectinload(SkillCategory.skills)).where(SkillCategory.id == cat_id)
    )
    cat = result.scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    if data.name is not None:
        cat.name = data.name
    if data.color is not None:
        cat.color = data.color
    if data.sort_order is not None:
        cat.sort_order = data.sort_order
    await db.commit()
    await db.refresh(cat, attribute_names=["skills"])
    return cat


@router.delete("/categories/{cat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    cat_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await require_global_permission(Permission.SKILL_MANAGE_CATEGORIES, current_user, db)
    result = await db.execute(select(SkillCategory).where(SkillCategory.id == cat_id))
    cat = result.scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    await db.delete(cat)
    await db.commit()
    return None


# ══════════════════════════════════════════════════════════════════
#  SKILLS — Admin CRUD
# ══════════════════════════════════════════════════════════════════

@router.post("/skills", response_model=SkillResponse, status_code=status.HTTP_201_CREATED)
async def create_skill(
    data: SkillCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await require_global_permission(Permission.SKILL_CREATE, current_user, db)
    skill = Skill(
        category_id=data.category_id,
        name=data.name,
        description=data.description,
        sort_order=data.sort_order or 0,
    )
    db.add(skill)
    await db.commit()
    await db.refresh(skill)
    return skill


@router.put("/skills/{skill_id}", response_model=SkillResponse)
async def update_skill(
    skill_id: str,
    data: SkillUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await require_global_permission(Permission.SKILL_EDIT, current_user, db)
    result = await db.execute(select(Skill).where(Skill.id == skill_id))
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    for field in ["name", "description", "category_id", "sort_order"]:
        val = getattr(data, field, None)
        if val is not None:
            setattr(skill, field, val)
    await db.commit()
    await db.refresh(skill)
    return skill


@router.delete("/skills/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_skill(
    skill_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await require_global_permission(Permission.SKILL_DELETE, current_user, db)
    result = await db.execute(select(Skill).where(Skill.id == skill_id))
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    await db.delete(skill)
    await db.commit()
    return None


# ══════════════════════════════════════════════════════════════════
#  USER SKILLS
# ══════════════════════════════════════════════════════════════════

@router.get("/users/average", response_model=List[UserSkillResponse])
async def get_average_skills(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the average skill level across all users for each skill."""
    await require_global_permission(Permission.SKILL_VIEW, current_user, db)
    avg_query = await db.execute(
        select(
            UserSkill.skill_id,
            func.avg(UserSkill.level).label("avg_level"),
        )
        .group_by(UserSkill.skill_id)
    )
    avg_map = {row.skill_id: round(float(row.avg_level), 2) for row in avg_query.all()}

    if not avg_map:
        return []

    skill_ids = list(avg_map.keys())
    result = await db.execute(
        select(Skill)
        .options(selectinload(Skill.category))
        .where(Skill.id.in_(skill_ids))
    )
    skills = result.scalars().all()

    return [
        UserSkillResponse(
            skill_id=s.id,
            skill_name=s.name,
            category_id=s.category_id,
            category_name=s.category.name,
            level=avg_map.get(s.id, 0),
        )
        for s in skills
    ]


def _normalize_user_skills(payload: List[UserSkillSet]) -> List[UserSkillSet]:
    """Validate growth-target rules and clamp levels.

    Rules:
      - level must be 0..3
      - If target_level is set, it must equal level + 1
      - level == 3 cannot have a target_level
      - If level >= target_level, the target is auto-cleared (not an error)
      - At most MAX_FOCUSES skills may have target_level set after normalization
    """
    seen_skill_ids: set[str] = set()
    normalized: List[UserSkillSet] = []
    focus_count = 0
    for s in payload:
        if s.skill_id in seen_skill_ids:
            raise HTTPException(status_code=400, detail=f"Duplicate skill_id in payload: {s.skill_id}")
        seen_skill_ids.add(s.skill_id)

        level = s.level
        if level < 0 or level > 3:
            raise HTTPException(status_code=400, detail=f"Invalid level {level} (must be 0-3)")

        target = s.target_level
        if target is not None:
            # Auto-clear stale targets where level has caught up
            if level >= target:
                target = None
            else:
                if target != level + 1:
                    raise HTTPException(
                        status_code=400,
                        detail="target_level must equal current level + 1 (one step at a time)",
                    )
                if level >= 3:
                    raise HTTPException(
                        status_code=400,
                        detail="Cannot set a growth target at maximum proficiency",
                    )
                focus_count += 1

        normalized.append(UserSkillSet(skill_id=s.skill_id, level=level, target_level=target))

    if focus_count > MAX_FOCUSES:
        raise HTTPException(
            status_code=400,
            detail=f"You can focus on at most {MAX_FOCUSES} skills at a time",
        )

    return normalized


@router.put("/users/me", response_model=List[UserSkillResponse])
async def set_my_skills(
    skills: List[UserSkillSet],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Bulk-set the current user's skill levels and (optional) growth targets."""
    skills = _normalize_user_skills(skills)

    await db.execute(delete(UserSkill).where(UserSkill.user_id == current_user.id))

    for s in skills:
        # Persist a row if it carries any signal (level > 0 OR a focus target).
        if s.level > 0 or s.target_level is not None:
            db.add(UserSkill(
                user_id=current_user.id,
                skill_id=s.skill_id,
                level=s.level,
                target_level=s.target_level,
            ))

    await db.commit()

    result = await db.execute(
        select(UserSkill)
        .options(selectinload(UserSkill.skill).selectinload(Skill.category))
        .where(UserSkill.user_id == current_user.id)
    )
    rows = result.scalars().all()
    return [
        UserSkillResponse(
            skill_id=r.skill_id,
            skill_name=r.skill.name,
            category_id=r.skill.category_id,
            category_name=r.skill.category.name,
            level=r.level,
            target_level=r.target_level,
        )
        for r in rows
    ]


@router.get("/users/{user_id}", response_model=List[UserSkillResponse])
async def get_user_skills(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Self-view is always allowed. Cross-user reads expose private growth
    # targets, so they're limited to roles that already see them via
    # /skills/focus-fit (admins and team leads). The global SKILL_VIEW
    # permission is seeded into the Default group and would not gate this.
    if user_id != current_user.id:
        if current_user.role not in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]:
            raise HTTPException(status_code=403, detail="Cannot view another user's skill profile")
    result = await db.execute(
        select(UserSkill)
        .options(selectinload(UserSkill.skill).selectinload(Skill.category))
        .where(UserSkill.user_id == user_id)
    )
    rows = result.scalars().all()
    return [
        UserSkillResponse(
            skill_id=r.skill_id,
            skill_name=r.skill.name,
            category_id=r.skill.category_id,
            category_name=r.skill.category.name,
            level=r.level,
            target_level=r.target_level,
        )
        for r in rows
    ]


# ══════════════════════════════════════════════════════════════════
#  GROWTH FOCUS-FIT (manage roles)
# ══════════════════════════════════════════════════════════════════

@router.get("/focus-fit", response_model=List[EngagementFocusFit])
async def get_focus_fit(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """For each engagement, list users whose growth-focus skills overlap the
    engagement's required skills.

    - ADMIN / TEAM_LEAD see matches across all users.
    - Operators only see their own matches (their growth focuses are private).
    """
    is_manage = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]

    focus_query = (
        select(UserSkill)
        .options(selectinload(UserSkill.user), selectinload(UserSkill.skill))
        .where(UserSkill.target_level.is_not(None))
    )
    if not is_manage:
        focus_query = focus_query.where(UserSkill.user_id == current_user.id)

    focuses = await db.execute(focus_query)
    focus_rows = focuses.scalars().all()

    # user_id -> {skill_id -> skill_name}
    user_focus_skills: dict[str, dict[str, str]] = {}
    user_meta: dict[str, User] = {}
    for r in focus_rows:
        user_focus_skills.setdefault(r.user_id, {})[r.skill_id] = r.skill.name if r.skill else ""
        if r.user is not None:
            user_meta[r.user_id] = r.user

    # Load all engagement-required skills
    eng_skills = await db.execute(select(EngagementSkill))
    eng_skill_rows = eng_skills.scalars().all()
    eng_required: dict[str, set[str]] = {}
    for es in eng_skill_rows:
        eng_required.setdefault(es.engagement_id, set()).add(es.skill_id)

    # Build response
    results: List[EngagementFocusFit] = []
    for eng_id, required in eng_required.items():
        matches: List[FocusFitMatch] = []
        for user_id, focus_map in user_focus_skills.items():
            overlap_ids = set(focus_map.keys()) & required
            if overlap_ids:
                u = user_meta.get(user_id)
                matches.append(FocusFitMatch(
                    user_id=user_id,
                    full_name=u.full_name if u else None,
                    username=u.username if u else "",
                    profile_photo=u.profile_photo if u else None,
                    matching_skills=[FocusFitSkill(id=sid, name=focus_map[sid]) for sid in overlap_ids],
                ))
        if matches:
            results.append(EngagementFocusFit(engagement_id=eng_id, matches=matches))

    return results


# ══════════════════════════════════════════════════════════════════
#  ENGAGEMENT SKILLS
# ══════════════════════════════════════════════════════════════════

@router.get("/engagements/{engagement_id}", response_model=List[EngagementSkillResponse])
async def get_engagement_skills(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await require_global_permission(Permission.SKILL_VIEW, current_user, db)
    result = await db.execute(
        select(EngagementSkill)
        .options(selectinload(EngagementSkill.skill).selectinload(Skill.category))
        .where(EngagementSkill.engagement_id == engagement_id)
    )
    rows = result.scalars().all()
    return [
        EngagementSkillResponse(
            skill_id=r.skill_id,
            skill_name=r.skill.name,
            category_id=r.skill.category_id,
            category_name=r.skill.category.name,
            min_level=r.min_level,
        )
        for r in rows
    ]


@router.put("/engagements/{engagement_id}", response_model=List[EngagementSkillResponse])
async def set_engagement_skills(
    engagement_id: str,
    skills: List[EngagementSkillSet],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Bulk-set required skills for an engagement."""
    await require_global_permission(Permission.SKILL_EDIT, current_user, db)

    # Delete existing
    await db.execute(delete(EngagementSkill).where(EngagementSkill.engagement_id == engagement_id))

    # Insert new
    for s in skills:
        db.add(EngagementSkill(engagement_id=engagement_id, skill_id=s.skill_id, min_level=s.min_level))

    await db.commit()

    # Return updated
    result = await db.execute(
        select(EngagementSkill)
        .options(selectinload(EngagementSkill.skill).selectinload(Skill.category))
        .where(EngagementSkill.engagement_id == engagement_id)
    )
    rows = result.scalars().all()
    return [
        EngagementSkillResponse(
            skill_id=r.skill_id,
            skill_name=r.skill.name,
            category_id=r.skill.category_id,
            category_name=r.skill.category.name,
            min_level=r.min_level,
        )
        for r in rows
    ]


# ══════════════════════════════════════════════════════════════════
#  SEED DEFAULT SKILLS
# ══════════════════════════════════════════════════════════════════

@router.post("/seed", status_code=status.HTTP_201_CREATED)
async def seed_skills(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Seed default skill categories and skills (admin only)."""
    await require_global_permission(Permission.SKILL_MANAGE_CATEGORIES, current_user, db)

    # Check if already seeded
    existing = await db.execute(select(SkillCategory))
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="Skills data already exists. Delete existing categories first.")

    seed_data = {
        ("Offensive", "#ef4444"): [
            "Web Application Testing",
            "Network Penetration Testing",
            "Wireless Security",
            "Social Engineering",
            "Physical Security",
            "Mobile Application Testing",
            "API Testing",
            "Red Team Operations",
        ],
        ("Defensive", "#3b82f6"): [
            "Incident Response",
            "Threat Hunting",
            "SIEM / Log Analysis",
            "Malware Analysis",
            "Digital Forensics",
            "Blue Team Operations",
        ],
        ("Cloud & Infrastructure", "#10b981"): [
            "AWS Security",
            "Azure Security",
            "GCP Security",
            "Kubernetes Security",
            "Container Security",
            "IaC Review (Terraform/CloudFormation)",
        ],
        ("Compliance & GRC", "#f59e0b"): [
            "PCI DSS",
            "HIPAA",
            "SOC 2",
            "ISO 27001",
            "NIST Framework",
            "Risk Assessment",
        ],
        ("Development & Scripting", "#8b5cf6"): [
            "Python",
            "Exploit Development",
            "Tool Development",
            "Reverse Engineering",
            "Scripting (Bash/PowerShell)",
            "C/C++",
        ],
    }

    for idx, ((cat_name, cat_color), skill_names) in enumerate(seed_data.items()):
        cat = SkillCategory(name=cat_name, color=cat_color, sort_order=idx)
        db.add(cat)
        await db.flush()
        for sidx, sname in enumerate(skill_names):
            db.add(Skill(category_id=cat.id, name=sname, sort_order=sidx))

    await db.commit()
    return {"detail": f"Seeded {len(seed_data)} categories with skills"}
