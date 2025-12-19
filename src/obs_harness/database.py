"""Database setup and session management for OBS Harness."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

# Global engine reference (set by init_db)
_engine = None


async def init_db(db_url: str = "sqlite+aiosqlite:///obs_harness.db") -> None:
    """Initialize the database engine and create tables."""
    global _engine

    # Ensure directory exists for file-based SQLite
    if "sqlite" in db_url and ":///" in db_url:
        db_path = db_url.split(":///")[-1]
        if db_path and db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    _engine = create_async_engine(
        db_url,
        echo=False,
        future=True,
    )

    async with _engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

        # Run migrations for existing tables (SQLite doesn't support IF NOT EXISTS for columns)
        migrations = [
            "ALTER TABLE character ADD COLUMN persist_memory BOOLEAN DEFAULT 0",
            # TTS provider abstraction migrations
            "ALTER TABLE character ADD COLUMN tts_provider TEXT DEFAULT 'elevenlabs'",
            "ALTER TABLE character ADD COLUMN tts_settings TEXT DEFAULT NULL",
        ]
        for migration in migrations:
            try:
                await conn.execute(text(migration))
            except Exception:
                pass  # Column already exists


async def close_db() -> None:
    """Close the database engine."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None


def get_session_factory() -> sessionmaker:
    """Get the async session factory."""
    if _engine is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")

    return sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get an async database session."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
