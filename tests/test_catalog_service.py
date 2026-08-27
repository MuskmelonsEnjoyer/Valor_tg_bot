import unittest
from unittest.mock import AsyncMock, patch

from app.services.catalog_service import load_unified_catalog, merge_instrument_catalogs


class UnifiedCatalogTests(unittest.TestCase):
    def test_t_invest_price_overrides_moex_for_same_isin(self):
        shares = {
            "SBER": {
                "isin": "RU0009029540",
                "name": "Сбербанк",
                "currency": "RUB",
                "last_price": 300.0,
                "price_source": "trade",
            }
        }
        broker = [
            {
                "secid": "SBER@TQBR",
                "ticker": "SBER",
                "isin": "RU0009029540",
                "uid": "broker-uid",
                "figi": "BBG004730N88",
                "name": "Сбер Банк",
                "currency": "RUB",
                "instrument_type": "share",
                "asset_type": "share",
                "last_price": 305.5,
                "last": 305.5,
                "price_source": "t_invest",
                "api_trade_available": True,
                "sources": ["t_invest"],
            }
        ]

        result = merge_instrument_catalogs(shares, {}, broker)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["secid"], "SBER")
        self.assertEqual(result[0]["last_price"], 305.5)
        self.assertEqual(result[0]["price_source"], "t_invest")
        self.assertEqual(result[0]["sources"], ["moex", "t_invest"])

    def test_moex_price_remains_when_broker_has_no_price(self):
        shares = {
            "SBER": {
                "isin": "RU0009029540",
                "name": "Сбербанк",
                "currency": "RUB",
                "last_price": 300.0,
                "price_source": "trade",
            }
        }
        broker = [
            {
                "secid": "SBER@TQBR",
                "ticker": "SBER",
                "isin": "RU0009029540",
                "uid": "broker-uid",
                "instrument_type": "share",
                "asset_type": "share",
                "currency": "RUB",
                "sources": ["t_invest"],
            }
        ]

        result = merge_instrument_catalogs(shares, {}, broker)

        self.assertEqual(result[0]["last_price"], 300.0)
        self.assertEqual(result[0]["price_source"], "trade")

    def test_broker_only_spb_instrument_is_added(self):
        broker = [
            {
                "secid": "AAPL@SPBXM",
                "ticker": "AAPL",
                "isin": "US0378331005",
                "uid": "spb-uid",
                "figi": "BBG000B9XRY4",
                "name": "Apple",
                "class_code": "SPBXM",
                "exchange": "SPB",
                "currency": "USD",
                "instrument_type": "share",
                "asset_type": "share",
                "last_price": 230.25,
                "price_source": "t_invest",
                "api_trade_available": True,
                "sources": ["t_invest"],
            }
        ]

        result = merge_instrument_catalogs({}, {}, broker)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["secid"], "AAPL@SPBXM")
        self.assertEqual(result[0]["exchange"], "SPB")
        self.assertEqual(result[0]["price_source"], "t_invest")

    def test_same_ticker_with_different_isin_is_not_merged(self):
        shares = {
            "TEST": {
                "isin": "RU0000000001",
                "name": "MOEX asset",
                "currency": "RUB",
            }
        }
        broker = [
            {
                "secid": "TEST@SPBXM",
                "ticker": "TEST",
                "isin": "US0000000001",
                "uid": "different-uid",
                "name": "SPB asset",
                "currency": "USD",
                "instrument_type": "share",
                "asset_type": "share",
                "sources": ["t_invest"],
            }
        ]

        result = merge_instrument_catalogs(shares, {}, broker)

        self.assertEqual(len(result), 2)
        self.assertEqual(
            {item["isin"] for item in result},
            {"RU0000000001", "US0000000001"},
        )


class UnifiedCatalogFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_uses_moex_when_t_invest_fails(self):
        moex = ({"SBER": {"isin": "RU0009029540", "currency": "RUB"}}, {})
        with (
            patch(
                "app.services.api_moex.parsing_instruments",
                AsyncMock(return_value=moex),
            ),
            patch(
                "app.services.t_invest.get_broker_instruments",
                AsyncMock(side_effect=RuntimeError("broker unavailable")),
            ),
        ):
            result = await load_unified_catalog("token")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["sources"], ["moex"])

    async def test_uses_t_invest_when_moex_fails(self):
        broker = [
            {
                "secid": "AAPL@SPBXM",
                "ticker": "AAPL",
                "isin": "US0378331005",
                "uid": "uid",
                "currency": "USD",
                "instrument_type": "share",
                "sources": ["t_invest"],
            }
        ]
        with (
            patch(
                "app.services.api_moex.parsing_instruments",
                AsyncMock(side_effect=RuntimeError("MOEX unavailable")),
            ),
            patch(
                "app.services.t_invest.get_broker_instruments",
                AsyncMock(return_value=broker),
            ),
        ):
            result = await load_unified_catalog("token")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["sources"], ["t_invest"])

    async def test_raises_when_both_sources_fail(self):
        with (
            patch(
                "app.services.api_moex.parsing_instruments",
                AsyncMock(side_effect=RuntimeError("MOEX unavailable")),
            ),
            patch(
                "app.services.t_invest.get_broker_instruments",
                AsyncMock(side_effect=RuntimeError("broker unavailable")),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "Neither MOEX nor T-Invest"):
                await load_unified_catalog("token")


if __name__ == "__main__":
    unittest.main()
