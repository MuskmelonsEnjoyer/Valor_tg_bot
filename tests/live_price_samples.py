"""Manual live-price roundtrip for representative MOEX shares."""

import asyncio
import json

from app.core.settings import Settings
from app.database import requests
from app.database.session import on_shutdown, on_startup
from app.services.instrument_price_service import refresh_and_store_instrument
from app.services.t_invest import configure_market_data_token, configure_t_invest_tls


TICKERS = ("SBER", "LKOH", "GAZP", "ROSN", "YDEX")


async def main() -> None:
    settings = Settings.from_env(require_telegram_token=False)
    configure_t_invest_tls(settings.t_invest_use_russian_ca)
    configure_market_data_token(settings.t_invest_token)
    report = {}
    try:
        await on_startup(settings.database_url)
        for ticker in TICKERS:
            instrument = await requests.find_inst_data(ticker)
            if instrument is None:
                report[ticker] = {"found": False}
                continue
            before_source = instrument.get("price_source")
            enriched = await refresh_and_store_instrument(instrument)
            report[ticker] = {
                "found": True,
                "before_source": before_source,
                "after_source": enriched.get("price_source"),
                "last_price": enriched.get("last_price") or enriched.get("last"),
                "has_uid": bool(enriched.get("uid")),
            }
    finally:
        await on_shutdown()

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
