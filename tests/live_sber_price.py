"""Manual SBER price roundtrip using the same path as the bot card."""

import asyncio
import json

from app.core.settings import Settings
from app.database import requests
from app.database.session import on_shutdown, on_startup
from app.services.instrument_price_service import refresh_and_store_instrument
from app.services.t_invest import configure_market_data_token, configure_t_invest_tls


async def main() -> None:
    settings = Settings.from_env(require_telegram_token=False)
    configure_t_invest_tls(settings.t_invest_use_russian_ca)
    configure_market_data_token(settings.t_invest_token)
    report = {}
    try:
        await on_startup(settings.database_url)
        instrument = await requests.find_inst_data("SBER")
        report["database_lookup"] = bool(instrument)
        if instrument is None:
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return

        report["before"] = {
            "price_source": instrument.get("price_source"),
            "last_price": instrument.get("last_price"),
            "last": instrument.get("last"),
            "has_uid": bool(instrument.get("uid")),
        }
        enriched = await refresh_and_store_instrument(instrument)
        report["after"] = {
            "price_source": enriched.get("price_source"),
            "last_price": enriched.get("last_price"),
            "last": enriched.get("last"),
            "has_uid": bool(enriched.get("uid")),
        }
        stored = await requests.find_inst_data("SBER")
        report["persisted"] = {
            "price_source": stored.get("price_source") if stored else None,
            "last_price": stored.get("last_price") if stored else None,
            "last": stored.get("last") if stored else None,
            "has_uid": bool(stored and stored.get("uid")),
        }

    finally:
        await on_shutdown()

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
