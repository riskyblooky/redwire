import asyncio
from sqlalchemy import select
from database import get_db
from models.user import User
from auth.password import verify_password

async def test_login():
    async for db in get_db():
        result = await db.execute(select(User).where(User.username == "admin"))
        user = result.scalar_one_or_none()
        
        if not user:
            print("User not found!")
            return
        
        print(f"Username: {user.username}")
        print(f"Hash from DB: '{user.hashed_password}'")
        print(f"Hash length: {len(user.hashed_password)}")
        print(f"Hash repr: {repr(user.hashed_password)}")
        
        password = "changeme"
        result = verify_password(password, user.hashed_password)
        print(f"Verification result: {result}")

asyncio.run(test_login())
