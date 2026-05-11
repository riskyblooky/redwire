from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://redwire:changeme@localhost:5432/redwire")
SQL_ECHO = os.getenv("SQL_ECHO", "false").lower() == "true"

# Create async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=SQL_ECHO,
    future=True,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

from sqlalchemy import Column, String, DateTime, ForeignKey
from datetime import datetime, timezone

# Base class for models
class Base(DeclarativeBase):
    pass

class AuditMixin:
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

# Dependency to get database session
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
