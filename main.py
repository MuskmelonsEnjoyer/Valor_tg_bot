import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from app.bot.handlers import router, set_commands
<<<<<<< HEAD
from app.core.config import TELEGRAM_TOKEN
from app.core.logger import logger_config
from app.database.session import on_shutdown, on_startup
=======
from app.core.logger import logger_config
from app.core.settings import Settings
from app.database.session import on_shutdown, on_startup
from app.services.instrument_refresh import (
    initialize_catalog_readiness,
    refresh_instruments_periodically,
)
from app.services.t_invest import configure_market_data_token, configure_t_invest_tls
>>>>>>> f04103d (version 1.0.0)


async def main():
    logger_config()
    logger = logging.getLogger("main")
<<<<<<< HEAD

    await on_startup()

    bot = Bot(
        token=TELEGRAM_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML)
=======
    settings = Settings.from_env()
    configure_t_invest_tls(settings.t_invest_use_russian_ca)
    configure_market_data_token(settings.t_invest_token)

    bot = Bot(
        token=settings.telegram_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
>>>>>>> f04103d (version 1.0.0)
    )
    dp = Dispatcher()
    dp.startup.register(set_commands)
    dp.include_router(router)

<<<<<<< HEAD
    dp.shutdown.register(on_shutdown)

    logger.info("Bot started!")
    await dp.start_polling(bot)
=======
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
>>>>>>> f04103d (version 1.0.0)


if __name__ == "__main__":
    asyncio.run(main())
