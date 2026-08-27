"""Live T-Invest -> PostgreSQL -> search smoke test.

The application may load its normal configuration, but this script never prints
configuration values, database URLs, tokens, or user identifiers.
"""

import asyncio
import json

import aiohttp
from sqlalchemy import func, select

from app.core.settings import Settings
from app.database import models, requests
from app.database.session import get_session_factory, on_shutdown, on_startup
from app.services.t_invest import enrich_with_latest_prices, find_broker_neoassets


async def main() -> None:
    report = {
        "configuration": {},
        "t_invest": {},
        "database": {},
        "delivery": {},
    }
    try:
        settings = Settings.from_env(require_telegram_token=False)
        report["configuration"]["global_t_invest_token_configured"] = bool(
            settings.t_invest_token
        )
        await on_startup(settings.database_url)

        async with get_session_factory()() as session:
            stored_token_count = await session.scalar(
                select(func.count()).select_from(models.UserToken)
            )
            stored_user_tokens = list(
                await session.scalars(
                    select(models.UserToken.user_t_invest_token)
                )
            )
        report["database"]["stored_user_tokens"] = int(stored_token_count or 0)

        token_candidates = []
        if settings.t_invest_token:
            token_candidates.append(("global_t_invest_token", settings.t_invest_token))
        for index, stored_user_token in enumerate(stored_user_tokens, start=1):
            if stored_user_token and stored_user_token not in {
                value for _, value in token_candidates
            }:
                token_candidates.append(
                    (f"stored_user_token_{index}", stored_user_token)
                )
        if not token_candidates:
            report["configuration"]["roundtrip_token_source"] = "none"
            report["t_invest"]["skipped"] = "no configured token"
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return

        try:
            async with aiohttp.ClientSession() as http_session:
                async with http_session.post(
                    "https://invest-public-api.tbank.ru/rest/"
                    "tinkoff.public.invest.api.contract.v1.InstrumentsService/"
                    "FindInstrument",
                    headers={"Authorization": f"Bearer {token_candidates[0][1]}"},
                    json={"query": "NBISperpA"},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    rest_payload = await response.json(content_type=None)
                    rest_instruments = rest_payload.get("instruments", [])
                    report["t_invest"]["rest_probe"] = {
                        "status": response.status,
                        "matching_rows": len(rest_instruments),
                        "nbisperpa_found": any(
                            str(item.get("ticker", "")).upper() == "NBISPERPA"
                            for item in rest_instruments
                        ),
                    }
        except aiohttp.ClientError as exc:
            # The application uses gRPC. A REST TLS issue should not prevent
            # the gRPC token and live-price checks below.
            report["t_invest"]["rest_probe"] = {
                "request_succeeded": False,
                "error_type": type(exc).__name__,
            }

        broker_rows = []
        token = None
        report["t_invest"]["token_attempts"] = {}
        for source, candidate_token in token_candidates:
            try:
                candidate_rows = await find_broker_neoassets(
                    "NBISperpA", candidate_token
                )
                report["t_invest"]["token_attempts"][source] = {
                    "request_succeeded": True,
                    "matching_rows": len(candidate_rows),
                }
                if candidate_rows and not broker_rows:
                    broker_rows = candidate_rows
                    token = candidate_token
                    report["configuration"]["roundtrip_token_source"] = source
            except Exception as exc:
                error_code = getattr(getattr(exc, "code", None), "name", None)
                error_details = str(getattr(exc, "details", "") or "")
                for _, secret_value in token_candidates:
                    error_details = error_details.replace(secret_value, "<redacted>")
                report["t_invest"]["token_attempts"][source] = {
                    "request_succeeded": False,
                    "error_type": type(exc).__name__,
                    "error_code": error_code,
                    "error_details": error_details[:300],
                }

        report["t_invest"]["nbisperpa_found"] = any(
            row.get("ticker") == "NBISPERPA" for row in broker_rows
        )
        report["t_invest"]["matching_rows"] = len(broker_rows)
        report["t_invest"]["price_received"] = any(
            row.get("price_source") == "t_invest" for row in broker_rows
        )

        written = await requests.upsert_instrument_catalog(broker_rows)
        report["database"]["rows_upserted"] = written

        search_rows, _ = await requests.search_instruments(
            "NBISperpA", "share", limit=8
        )
        report["database"]["search_found"] = bool(search_rows)
        report["database"]["stored_as_neoasset"] = bool(
            search_rows and search_rows[0].get("asset_type") == "neoasset"
        )
        report["database"]["stored_ticker_matches"] = bool(
            search_rows and search_rows[0].get("ticker") == "NBISPERPA"
        )

        if search_rows:
            delivered = (
                await enrich_with_latest_prices(search_rows[:1], token=token)
            )[0]
            report["delivery"]["read_from_database"] = True
            report["delivery"]["live_price_available"] = (
                delivered.get("price_source") == "t_invest"
                and delivered.get("last_price") is not None
            )
            report["delivery"]["name"] = delivered.get("name")
            report["delivery"]["currency"] = delivered.get("currency")
        else:
            report["delivery"]["read_from_database"] = False
    except Exception as exc:
        report["error_type"] = type(exc).__name__
    finally:
        await on_shutdown()

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
