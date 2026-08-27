import asyncio
import logging

from app.core.logger import logger_config
from app.core.settings import Settings
from app.database.requests import upload_bonds_shares
from app.database.session import on_shutdown, on_startup
from app.services.t_invest import configure_t_invest_tls


async def main() -> None:
    logger_config()
    logger = logging.getLogger("main")
    settings = Settings.from_env(require_telegram_token=False)
    configure_t_invest_tls(settings.t_invest_use_russian_ca)

    try:
        await on_startup(settings.database_url)
        await upload_bonds_shares(settings.t_invest_token)
        logger.info("Instrument catalog updated")
    finally:
        await on_shutdown()


if __name__ == "__main__":
    asyncio.run(main())
