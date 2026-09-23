"""
Database — async SQLAlchemy engine with asyncpg + Redis connection.
"""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import redis.asyncio as aioredis
import structlog
from sqlalchemy.ext.asyncio import (
    AsyncSession, AsyncEngine,
    async_sessionmaker, create_async_engine
)
from sqlalchemy.orm import DeclarativeBase

from config import settings

log = structlog.get_logger(__name__)


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


# ── Engine ───────────────────────────────────────────────────────────────────

engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=300,
    connect_args={
        "server_settings": {
            "application_name": "global_task_earn",
            "jit": "off",               # Disable JIT for short transactions
        }
    },
)

async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


# ── Redis ─────────────────────────────────────────────────────────────────────

_redis_pool: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    """Return the Redis connection pool. Must call init_db first."""
    if _redis_pool is None:
        raise RuntimeError("Redis not initialized. Call init_db() first.")
    return _redis_pool


# ── Lifecycle ─────────────────────────────────────────────────────────────────

async def init_db() -> None:
    """Initialize DB engine and Redis pool. Called at bot startup."""
    global _redis_pool

    # Test DB connection
    async with engine.connect() as conn:
        from sqlalchemy import text
        result = await conn.execute(text("SELECT 1"))
        log.info("PostgreSQL connection OK", version=str(result.scalar()))

    # Initialize Redis
    _redis_pool = aioredis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        max_connections=50,
    )
    await _redis_pool.ping()
    log.info("Redis connection OK")


async def close_db() -> None:
    """Close all connections on shutdown."""
    global _redis_pool
    await engine.dispose()
    if _redis_pool:
        await _redis_pool.aclose()
        _redis_pool = None
    log.info("Database connections closed")


# ── Session context manager ───────────────────────────────────────────────────

@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactional database session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Alias for get_session — use in dependency injection."""
    async with get_session() as session:
        yield session
