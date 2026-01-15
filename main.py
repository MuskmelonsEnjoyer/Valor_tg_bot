import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.core.config import TELEGRAM_TOKEN
from app.core.logger import logger_config
from app.database.session import on_startup, on_shutdown
from app.bot.handlers import router as bot_router

async def main():

    logger_config()
    logger = logging.getLogger("main")
    
    await on_startup()
    
    bot = Bot(token=TELEGRAM_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    
    dp.include_router(bot_router)
    
    dp.shutdown.register(on_shutdown)

    logger.info("Bot started!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())