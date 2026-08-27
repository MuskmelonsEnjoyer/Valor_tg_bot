"""Manual live smoke test. Reads process environment only; never loads .env."""

import asyncio
import json
import os
from collections import Counter

from app.services.api_moex import parsing_instruments
from app.services.catalog_service import merge_instrument_catalogs
from app.services.t_invest import get_broker_instruments


def _duplicate_values(items: list[dict], field: str) -> int:
    values = [str(item[field]).upper() for item in items if item.get(field)]
    return sum(count - 1 for count in Counter(values).values() if count > 1)


async def main() -> None:
    shares, bonds = await parsing_instruments()
    moex_rows = merge_instrument_catalogs(shares, bonds, [])
    report = {
        "moex": {
            "shares": len(shares),
            "bonds": len(bonds),
            "duplicate_isin_rows": _duplicate_values(moex_rows, "isin"),
            "without_price": sum(
                1 for item in moex_rows if item.get("last_price") is None
            ),
            "fallback_eligible_without_price": sum(
                1
                for item in moex_rows
                if item.get("last_price") is None
                and (
                    item.get("prev_price") is not None
                    or item.get("prev_price_percent") is not None
                )
            ),
        }
    }

    token = os.environ.get("T_INVEST_TOKEN", "").strip()
    if token:
        broker_rows = await get_broker_instruments(token)
        unified = merge_instrument_catalogs(shares, bonds, broker_rows)
        report["t_invest"] = {
            "instruments": len(broker_rows),
            "neoassets": sum(
                1 for item in broker_rows if item.get("asset_type") == "neoasset"
            ),
            "nbisperpa_found": any(
                item.get("ticker") == "NBISPERPA" for item in broker_rows
            ),
            "with_price": sum(
                1 for item in broker_rows if item.get("price_source") == "t_invest"
            ),
            "duplicate_isin_rows": _duplicate_values(broker_rows, "isin"),
        }
        report["unified"] = {
            "instruments": len(unified),
            "duplicate_secid_rows": _duplicate_values(unified, "secid"),
            "duplicate_isin_rows": _duplicate_values(unified, "isin"),
            "t_invest_prices": sum(
                1 for item in unified if item.get("price_source") == "t_invest"
            ),
            "moex_fallback_prices": sum(
                1
                for item in unified
                if item.get("price_source") not in {None, "t_invest"}
            ),
        }
    else:
        report["t_invest"] = {"skipped": "T_INVEST_TOKEN is not exported"}

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
