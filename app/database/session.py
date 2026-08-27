import logging
import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from app.database.models import Base
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

logger = logging.getLogger("database")

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def configure_database(database_url: str) -> AsyncEngine:
    global _engine, _session_factory

    if _engine is None:
        _engine = create_async_engine(database_url, echo=False, pool_pre_ping=True)
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)

    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("Database is not configured. Call on_startup() first.")
    return _session_factory

# Инициализация базы данных.
async def init_db(database_url: str) -> None:
    configure_database(database_url)
    await run_migrations(database_url)


async def run_migrations(database_url: str) -> None:
    """Apply checked-in Alembic revisions using the configured async URL."""
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    # Alembic's fileConfig sets the root level to WARNING. When migrations run
    # inside the bot process that would silently disable all application INFO
    # records configured by logger_config(). Direct CLI migrations keep their
    # normal Alembic logging because this attribute is not present there.
    config.attributes["configure_logger"] = False
    await asyncio.to_thread(command.upgrade, config, "head")

# Функция, которая сработает при старте
async def on_startup(database_url: str) -> None:
    logger.info("Starting database...")
    await init_db(database_url)

# Функция, которая сработает при остановке (например, закрыть соединение)
async def on_shutdown() -> None:
    global _engine, _session_factory

    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
