"""Seed user skills for all existing users with realistic distributions."""
import asyncio
import random
import os
import sys

# Make sure we can import from the backend
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from database import AsyncSessionLocal
from models.user import User
from models.skill import Skill, SkillCategory, UserSkill


async def seed_user_skills():
    async with AsyncSessionLocal() as db:
        # Fetch all users and skills
        users = (await db.execute(select(User).where(User.is_active == True))).scalars().all()
        categories = (await db.execute(
            select(SkillCategory).order_by(SkillCategory.sort_order)
        )).scalars().all()
        skills = (await db.execute(select(Skill))).scalars().all()

        if not users:
            print("No users found!")
            return
        if not skills:
            print("No skills found!")
            return

        print(f"Found {len(users)} users and {len(skills)} skills across {len(categories)} categories")

        # Build category -> skills map
        cat_skills: dict[str, list] = {}
        for s in skills:
            cat_skills.setdefault(s.category_id, []).append(s)

        # Clear existing user skills
        await db.execute(delete(UserSkill))
        print("Cleared existing user skills")

        # For each user, assign skills with varying profiles
        # Some users are specialists (high in 1-2 categories), some are generalists
        profiles = [
            "specialist_offensive",
            "specialist_defensive",
            "generalist",
            "senior_all_rounder",
            "cloud_focused",
            "scripting_heavy",
        ]

        count = 0
        for i, user in enumerate(users):
            profile = profiles[i % len(profiles)]
            print(f"  Seeding skills for {user.full_name or user.username} (profile: {profile})")

            for cat in categories:
                cat_skill_list = cat_skills.get(cat.id, [])
                if not cat_skill_list:
                    continue

                cat_name_lower = cat.name.lower()

                # Determine base level range for this category based on profile
                if profile == "specialist_offensive":
                    if "offensive" in cat_name_lower:
                        level_range = (2, 3)
                    elif "script" in cat_name_lower or "develop" in cat_name_lower:
                        level_range = (1, 2)
                    else:
                        level_range = (0, 1)
                elif profile == "specialist_defensive":
                    if "defensive" in cat_name_lower:
                        level_range = (2, 3)
                    elif "compliance" in cat_name_lower or "grc" in cat_name_lower:
                        level_range = (1, 3)
                    else:
                        level_range = (0, 1)
                elif profile == "cloud_focused":
                    if "cloud" in cat_name_lower or "infra" in cat_name_lower:
                        level_range = (2, 3)
                    elif "defensive" in cat_name_lower:
                        level_range = (1, 2)
                    else:
                        level_range = (0, 1)
                elif profile == "scripting_heavy":
                    if "script" in cat_name_lower or "develop" in cat_name_lower:
                        level_range = (2, 3)
                    elif "offensive" in cat_name_lower:
                        level_range = (1, 2)
                    else:
                        level_range = (0, 1)
                elif profile == "senior_all_rounder":
                    level_range = (1, 3)
                else:  # generalist
                    level_range = (0, 2)

                for skill in cat_skill_list:
                    level = random.randint(level_range[0], level_range[1])
                    # Skip level 0 sometimes to keep it sparse
                    if level == 0 and random.random() < 0.5:
                        continue
                    db.add(UserSkill(
                        user_id=user.id,
                        skill_id=skill.id,
                        level=level,
                    ))
                    count += 1

        await db.commit()
        print(f"\nSeeded {count} user skill entries across {len(users)} users!")


if __name__ == "__main__":
    asyncio.run(seed_user_skills())
