"""Database setup and session management for OBS Harness."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

logger = logging.getLogger(__name__)

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
            # Multi-tenancy migrations - add tenant_id columns
            "ALTER TABLE character ADD COLUMN tenant_id TEXT DEFAULT 'default'",
            "ALTER TABLE textpreset ADD COLUMN tenant_id TEXT DEFAULT 'default'",
            "ALTER TABLE playbacklog ADD COLUMN tenant_id TEXT DEFAULT 'default'",
            "ALTER TABLE twitchconfig ADD COLUMN tenant_id TEXT DEFAULT 'default'",
            "ALTER TABLE conversationmessage ADD COLUMN tenant_id TEXT DEFAULT 'default'",
            "ALTER TABLE santaconfig ADD COLUMN tenant_id TEXT DEFAULT 'default'",
            "ALTER TABLE santasession ADD COLUMN tenant_id TEXT DEFAULT 'default'",
        ]
        for migration in migrations:
            try:
                await conn.execute(text(migration))
            except OperationalError as e:
                # SQLite raises OperationalError for "duplicate column name"
                if "duplicate column" in str(e).lower():
                    pass  # Column already exists, expected
                else:
                    logger.error(f"Migration failed: {migration!r} - {e}")
            except Exception as e:
                logger.error(f"Unexpected error during migration: {migration!r} - {e}")

        # Create composite unique indexes for multi-tenancy
        # These ensure uniqueness per tenant for name fields
        index_migrations = [
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_character_tenant_name ON character(tenant_id, name)",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_textpreset_tenant_name ON textpreset(tenant_id, name)",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_twitchconfig_tenant ON twitchconfig(tenant_id)",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_santaconfig_tenant ON santaconfig(tenant_id)",
            # Standard indexes for tenant_id filtering
            "CREATE INDEX IF NOT EXISTS ix_character_tenant ON character(tenant_id)",
            "CREATE INDEX IF NOT EXISTS ix_textpreset_tenant ON textpreset(tenant_id)",
            "CREATE INDEX IF NOT EXISTS ix_playbacklog_tenant ON playbacklog(tenant_id)",
            "CREATE INDEX IF NOT EXISTS ix_conversationmessage_tenant ON conversationmessage(tenant_id)",
            "CREATE INDEX IF NOT EXISTS ix_santasession_tenant ON santasession(tenant_id)",
        ]
        for migration in index_migrations:
            try:
                await conn.execute(text(migration))
            except OperationalError as e:
                # IF NOT EXISTS should prevent errors, but log if something else fails
                if "already exists" in str(e).lower():
                    pass  # Index already exists, expected
                else:
                    logger.error(f"Index creation failed: {migration!r} - {e}")
            except Exception as e:
                logger.error(f"Unexpected error during index creation: {migration!r} - {e}")


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
