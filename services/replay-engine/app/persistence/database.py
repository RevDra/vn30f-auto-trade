"""Async database engine + session factory (SQLAlchemy 2.0)."""

import os
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger("replay-engine.db")


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
    pass


class DatabaseManager:
    """Manages the async database lifecycle."""

    def __init__(self, url: Optional[str] = None):
        self._url = url or self._build_url()
        self._engine: Optional[AsyncEngine] = None
        self._session_factory: Optional[async_sessionmaker[AsyncSession]] = None

    @staticmethod
    def _build_url() -> str:
        """Build DB URL from environment variables."""
        driver = os.getenv("DB_DRIVER", "mysql+aiomysql")
        host = os.getenv("MYSQL_HOST", "localhost")
        port = os.getenv("MYSQL_PORT", "3306")
        user = os.getenv("MYSQL_USER", "root")
        password = os.getenv("MYSQL_ROOT_PASSWORD", "rootpass")
        db = os.getenv("MYSQL_DATABASE", "vn30f1m_db")
        return f"{driver}://{user}:{password}@{host}:{port}/{db}"

    async def init(self, echo: bool = False):
        """Create engine, session factory, and run DDL."""
        engine_kwargs = {
            "echo": echo,
            "pool_pre_ping": True,
        }

        # SQLite doesn't support pool_size/max_overflow
        if "sqlite" not in self._url:
            engine_kwargs["pool_size"] = 5
            engine_kwargs["max_overflow"] = 10

        self._engine = create_async_engine(self._url, **engine_kwargs)
        self._session_factory = async_sessionmaker(
            self._engine, expire_on_commit=False
        )

        # Create tables if they don't exist
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database initialized: %s", self._url.split("@")[-1] if "@" in self._url else self._url)

    @property
    def engine(self) -> AsyncEngine:
        if self._engine is None:
            raise RuntimeError("DatabaseManager not initialized — call await init() first")
        return self._engine

    def session(self) -> AsyncSession:
        """Return a new async session."""
        if self._session_factory is None:
            raise RuntimeError("DatabaseManager not initialized — call await init() first")
        return self._session_factory()

    async def close(self):
        if self._engine:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None
            logger.info("Database connection closed")
