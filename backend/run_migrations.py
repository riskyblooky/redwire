#!/usr/bin/env python3
"""Run database migrations"""
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))

from alembic import command
from alembic.config import Config

def run_migrations():
    """Run all database migrations"""
    # Get the alembic configuration
    alembic_cfg = Config("alembic.ini")
    
    # Run the migrations
    print("Running database migrations...")
    command.upgrade(alembic_cfg, "head")
    print("✅ Database migrations completed successfully!")

if __name__ == "__main__":
    run_migrations()
