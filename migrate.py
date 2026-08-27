import asyncio

from app.core.settings import Settings
from app.database.session import run_migrations


async def main() -> None:
    settings = Settings.from_env(require_telegram_token=False)
    await run_migrations(settings.database_url)
    print("Database migrations applied")


if __name__ == "__main__":
    asyncio.run(main())
