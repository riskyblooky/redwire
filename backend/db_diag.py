import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def test():
    db_url = os.getenv('DATABASE_URL')
    print(f"Testing DB URL: {db_url}")
    engine = create_async_engine(db_url)
    try:
        async with engine.connect() as conn:
            res = await conn.execute(text("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = 'public'"))
            tables = res.fetchall()
            print(f"Tables found: {[t[0] for t in tables]}")
            
            if 'users' in [t[0] for t in tables]:
                res = await conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'users'"))
                columns = res.fetchall()
                print(f"Columns in 'users': {[c[0] for c in columns]}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(test())
