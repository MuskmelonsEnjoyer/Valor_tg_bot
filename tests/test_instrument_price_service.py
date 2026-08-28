import unittest
from unittest.mock import AsyncMock, patch

from app.services.instrument_price_service import refresh_and_store_instrument
from app.services.t_invest import MarketDataTokenCandidate


class InstrumentPriceServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_t_invest_price_is_returned_and_persisted(self):
        stored = {
            "secid": "SBER",
            "isin": "RU0009029540",
            "instrument_type": "share",
            "last_price": 300.0,
            "price_source": "trade",
        }
        enriched = {
            **stored,
            "uid": "resolved-uid",
            "last": 321.5,
            "last_price": 321.5,
            "price_source": "t_invest",
        }

        with (
            patch(
                "app.services.instrument_price_service.enrich_with_latest_prices",
                new=AsyncMock(return_value=[enriched]),
            ) as refresh,
            patch(
                "app.services.instrument_price_service.requests.upsert_instrument_catalog",
                new=AsyncMock(return_value=1),
            ) as upsert,
        ):
            result = await refresh_and_store_instrument(
                stored,
                token="user-token",
            )

        refresh.assert_awaited_once_with([stored], token="user-token")
        upsert.assert_awaited_once_with([enriched])
        self.assertEqual(result["last_price"], 321.5)
        self.assertEqual(result["price_source"], "t_invest")

    async def test_moex_fallback_is_not_rewritten_without_t_invest_data(self):
        stored = {
            "secid": "SBER",
            "instrument_type": "share",
            "last_price": 300.0,
            "price_source": "trade",
        }

        with (
            patch(
                "app.services.instrument_price_service.enrich_with_latest_prices",
                new=AsyncMock(return_value=[stored]),
            ),
            patch(
                "app.services.instrument_price_service.requests.upsert_instrument_catalog",
                new=AsyncMock(return_value=1),
            ) as upsert,
        ):
            result = await refresh_and_store_instrument(stored, token="user-token")

        upsert.assert_not_awaited()
        self.assertEqual(result, stored)

    async def test_user_id_resolves_db_and_system_fallback_candidates(self):
        stored = {
            "secid": "SBER",
            "instrument_type": "share",
            "last_price": 300.0,
            "price_source": "trade",
        }
        candidates = (
            MarketDataTokenCandidate("user-token", "user"),
            MarketDataTokenCandidate("system-token", "system"),
        )

        with (
            patch(
                "app.services.instrument_price_service.resolve_market_data_tokens",
                new=AsyncMock(return_value=candidates),
            ) as resolve_tokens,
            patch(
                "app.services.instrument_price_service.discard_rejected_user_token",
                new=AsyncMock(return_value=True),
            ) as discard_token,
            patch(
                "app.services.instrument_price_service.enrich_with_latest_prices",
                new=AsyncMock(return_value=[stored]),
            ) as refresh,
            patch(
                "app.services.instrument_price_service.requests.upsert_instrument_catalog",
                new=AsyncMock(return_value=1),
            ),
        ):
            result = await refresh_and_store_instrument(stored, user_id=42)
            callback = refresh.await_args.kwargs["on_unauthenticated"]
            await callback(candidates[0])

        resolve_tokens.assert_awaited_once_with(42)
        self.assertEqual(
            refresh.await_args.kwargs["token_candidates"],
            candidates,
        )
        discard_token.assert_awaited_once_with(42, candidates[0])
        self.assertEqual(result, stored)


if __name__ == "__main__":
    unittest.main()
