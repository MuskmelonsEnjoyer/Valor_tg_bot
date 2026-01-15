from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import declarative_base
from app.core.config import DATABASE_URL

import logging

logger = logging.getLogger("database")

Base = declarative_base()
engine = create_async_engine(DATABASE_URL, echo=False)


# Инициализация базы данных.
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# Функция, которая сработает при старте
async def on_startup():
    logger.info("Starting database...")
    await init_db()


# Функция, которая сработает при остановке (например, закрыть соединение)
async def on_shutdown():
    await engine.dispose()
