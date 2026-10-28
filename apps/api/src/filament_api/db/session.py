"""Asynchronous database engine and session management."""

from collections.abc import AsyncGenerator
from typing import Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from filament_api.config import Settings, get_settings

_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def init_db_engine(settings: Optional[Settings] = None) -> AsyncEngine:
    """Initialize the global asynchronous SQLAlchemy engine and session factory."""
    global _engine, _session_factory
    cfg = settings or get_settings()

    _engine = create_async_engine(
        str(cfg.DATABASE_URL),
        pool_size=cfg.DATABASE_POOL_SIZE,
        max_overflow=cfg.DATABASE_MAX_OVERFLOW,
        pool_timeout=cfg.DATABASE_POOL_TIMEOUT,
        echo=cfg.DATABASE_ECHO,
        future=True,
    )
    _session_factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    return _engine


def get_engine() -> AsyncEngine:
    """Retrieve the initialized global AsyncEngine, initializing lazily if necessary."""
    global _engine
    if _engine is None:
        return init_db_engine()
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Retrieve the sessionmaker factory."""
    global _session_factory
    if _session_factory is None:
        init_db_engine()
    assert _session_factory is not None
    return _session_factory


async def close_db_engine() -> None:
    """Safely dispose of the database engine and active connection pool."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for yielding transactional database sessions.

    Ensures rollback on failure and clean closure after request completion.
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

