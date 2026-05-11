import asyncio
from database import AsyncSessionLocal, engine, Base
from models.group import Group
from models.engagement_role import EngagementRole
from sqlalchemy import select

async def seed_rbac():
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        print("Database tables created/verified.")

    async with AsyncSessionLocal() as db:
        # Seed Groups
        groups = [
            {"name": "Core Team", "description": "Full-time internal security researchers"},
            {"name": "External Contractors", "description": "Seasonal or project-based external help"},
            {"name": "Audit/Management", "description": "High-level oversight and reporting access"},
        ]
        
        for g_data in groups:
            result = await db.execute(select(Group).where(Group.name == g_data["name"]))
            if not result.scalar_one_or_none():
                db.add(Group(**g_data))
                print(f"Added group: {g_data['name']}")

        # Seed Engagement Roles
        roles = [
            {"name": "Engagement Lead", "description": "Overall responsibility for the engagement, final report approval"},
            {"name": "Operator", "description": "Active participant, can add findings and test cases"},
            {"name": "Observer", "description": "Read-only access to progress and findings"},
        ]

        for r_data in roles:
            result = await db.execute(select(EngagementRole).where(EngagementRole.name == r_data["name"]))
            if not result.scalar_one_or_none():
                db.add(EngagementRole(**r_data))
                print(f"Added role: {r_data['name']}")

        await db.commit()
        print("RBAC Seeding complete!")

if __name__ == "__main__":
    asyncio.run(seed_rbac())
