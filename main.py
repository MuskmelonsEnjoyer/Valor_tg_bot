import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from app.bot.handlers import router, set_commands
from app.core.logger import logger_config
from app.core.settings import Settings
from app.database.session import on_shutdown, on_startup
from app.services.instrument_refresh import (
    initialize_catalog_readiness,
    refresh_instruments_periodically,
)
from app.services.t_invest import configure_market_data_token, configure_t_invest_tls


async def main():
    logger_config()
    logger = logging.getLogger("main")
    settings = Settings.from_env()
    configure_t_invest_tls(settings.t_invest_use_russian_ca)
    configure_market_data_token(settings.t_invest_token)

    bot = Bot(
        token=settings.telegram_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.startup.register(set_commands)
    dp.include_router(router)

    refresh_task: asyncio.Task | None = None
    try:
        await on_startup(settings.database_url)
        await initialize_catalog_readiness()
        refresh_task = asyncio.create_task(
            refresh_instruments_periodically(
                settings.moex_refresh_interval_seconds,
                settings.t_invest_token,
            ),
            name="moex-instrument-refresh",
        )
        logger.info("Bot started!")
        await dp.start_polling(bot)
    finally:
        if refresh_task is not None:
            refresh_task.cancel()
            await asyncio.gather(refresh_task, return_exceptions=True)
        await on_shutdown()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
