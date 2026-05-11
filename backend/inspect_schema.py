import asyncio
from sqlalchemy import create_engine, inspect
from database import DB_URL

def inspect_db():
    engine = create_engine(DB_URL.replace("+asyncpg", "")) # Use sync engine for inspection
    inspector = inspect(engine)
    
    tables = ["findings", "assets", "testcases"]
    for table_name in tables:
        print(f"Table: {table_name}")
        columns = inspector.get_columns(table_name)
        for column in columns:
            print(f"  - {column['name']}: {column['type']}")

if __name__ == "__main__":
    try:
        inspect_db()
    except Exception as e:
        print(f"Error: {e}")
