import asyncio
from sqlalchemy import create_engine, text
from database import DB_URL
import os

def migrate():
    # Use sync engine for migration
    engine = create_engine(DB_URL.replace("+asyncpg", ""))
    
    with engine.connect() as conn:
        print("Checking for created_by in assets...")
        try:
            conn.execute(text("ALTER TABLE assets ADD COLUMN created_by VARCHAR"))
            print("Added created_by to assets")
            # Set a default user if there are existing assets
            # We'll just set it to the first user found or a dummy ID if needed
        except Exception as e:
            print(f"Assets created_by check/add failed (might already exist): {e}")
            
        print("Checking for created_by in testcases...")
        try:
            conn.execute(text("ALTER TABLE testcases ADD COLUMN created_by VARCHAR"))
            print("Added created_by to testcases")
        except Exception as e:
            print(f"Testcases created_by check/add failed: {e}")
            
        # Update existing records to avoid Null errors if nullable=False
        try:
            # Find first admin or user
            result = conn.execute(text("SELECT id FROM users LIMIT 1"))
            user_id = result.scalar()
            if user_id:
                conn.execute(text(f"UPDATE assets SET created_by = '{user_id}' WHERE created_by IS NULL"))
                conn.execute(text(f"UPDATE testcases SET created_by = '{user_id}' WHERE created_by IS NULL"))
                print(f"Updated existing records with user_id: {user_id}")
            
            # Now set to NOT NULL
            conn.execute(text("ALTER TABLE assets ALTER COLUMN created_by SET NOT NULL"))
            conn.execute(text("ALTER TABLE testcases ALTER COLUMN created_by SET NOT NULL"))
            print("Set created_by columns to NOT NULL")
        except Exception as e:
            print(f"Finalizing columns failed: {e}")
        
        conn.commit()
    print("Migration attempt finished.")

if __name__ == "__main__":
    migrate()
