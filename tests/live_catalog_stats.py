"""Print non-sensitive source statistics for the persisted instrument catalog."""

import asyncio
import json

from sqlalchemy import func, select

from app.core.settings import Settings
from app.database import models
from app.database.session import get_session_factory, on_shutdown, on_startup


async def main() -> None:
    settings = Settings.from_env(require_telegram_token=False)
    try:
        await on_startup(settings.database_url)
        async with get_session_factory()() as session:
            total = await session.scalar(
                select(func.count()).select_from(models.Instruments)
            )
            t_invest_prices = await session.scalar(
                select(func.count())
                .select_from(models.Instruments)
                .where(
                    models.Instruments.extra_data["price_source"].astext
                    == "t_invest"
                )
            )
            with_uid = await session.scalar(
                select(func.count())
                .select_from(models.Instruments)
                .where(models.Instruments.extra_data["uid"].astext.is_not(None))
            )
    finally:
        await on_shutdown()

    print(
        json.dumps(
            {
                "instruments": int(total or 0),
                "t_invest_prices": int(t_invest_prices or 0),
                "with_t_invest_uid": int(with_uid or 0),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
