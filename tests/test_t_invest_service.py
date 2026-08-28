import unittest
import os
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services.t_invest import (
    MarketDataTokenCandidate,
    _load_last_prices,
    _pack_instrument,
    configure_market_data_token,
    configure_t_invest_tls,
    enrich_with_latest_prices,
    find_broker_neoassets,
    get_broker_instruments,
)
from grpc import StatusCode
from t_tech.invest import LastPrice, MoneyValue, Quotation
from t_tech.invest.exceptions import AioUnauthenticatedError


class FakeMarketData:
    def __init__(self, prices):
        self.prices = prices
        self.requests = []

    async def get_last_prices(self, *, instrument_id):
        self.requests.append(instrument_id)
        return SimpleNamespace(last_prices=self.prices)


class FakeClient:
    def __init__(self, prices):
        self.market_data = FakeMarketData(prices)


class FakeCatalogClient:
    def __init__(self, _token):
        neoasset = SimpleNamespace(
            uid="neo-uid",
            figi="neo-figi",
            ticker="NBISperpA",
            name="Neo Nebius",
            class_code="SPBFUT",
            currency="usd",
            exchange="SPB",
        )
        regular_future = SimpleNamespace(
            uid="regular-uid",
            figi="regular-figi",
            ticker="SiU6",
            name="USD/RUB future",
            class_code="SPBFUT",
            currency="rub",
            exchange="MOEX",
        )
        empty = SimpleNamespace(instruments=[])
        self.instruments = SimpleNamespace(
            shares=self._response(empty),
            bonds=self._response(empty),
            etfs=self._response(empty),
            futures=self._response(
                SimpleNamespace(instruments=[neoasset, regular_future])
            ),
        )
        self.market_data = FakeMarketData([])

    @staticmethod
    def _response(value):
        async def call(**_kwargs):
            return value

        return call

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


class FakeSearchClient:
    received_tokens = []

    def __init__(self, token):
        self.received_tokens.append(token)
        short = SimpleNamespace(uid="neo-uid", ticker="NBISperpA")
        detail = SimpleNamespace(
            uid="neo-uid",
            figi="neo-figi",
            ticker="NBISperpA",
            name="Neo Nebius",
            class_code="SPBFUT",
            currency="usd",
            exchange="SPB",
        )
        self.instruments = SimpleNamespace(
            find_instrument=self._response(SimpleNamespace(instruments=[short])),
            future_by=self._response(SimpleNamespace(instrument=detail)),
        )
        self.market_data = FakeMarketData([])

    @staticmethod
    def _response(value):
        async def call(**_kwargs):
            return value

        return call

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


class FakeResolvingClient:
    received_tokens = []

    def __init__(self, token):
        self.received_tokens.append(token)
        instrument = SimpleNamespace(
            uid="resolved-uid",
            figi="resolved-figi",
            ticker="SBER",
            isin="RU0009029540",
        )
        self.instruments = SimpleNamespace(
            find_instrument=self._response(
                SimpleNamespace(instruments=[instrument])
            )
        )
        self.market_data = FakeMarketData(
            [
                LastPrice(
                    instrument_uid="resolved-uid",
                    price=Quotation(units=321, nano=500_000_000),
                    time=datetime(2026, 8, 27, 12, 0, tzinfo=UTC),
                )
            ]
        )

    @staticmethod
    def _response(value):
        async def call(**_kwargs):
            return value

        return call

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


class FakeFallbackClient:
    received_tokens = []

    def __init__(self, token):
        self.token = token
        self.received_tokens.append(token)
        self.market_data = FakeMarketData(
            [
                LastPrice(
                    instrument_uid="resolved-uid",
                    price=Quotation(units=321, nano=500_000_000),
                    time=datetime(2026, 8, 27, 12, 0, tzinfo=UTC),
                )
            ]
        )

    async def __aenter__(self):
        if self.token == "rejected-user-token":
            raise AioUnauthenticatedError(
                StatusCode.UNAUTHENTICATED,
                "40003",
                None,
            )
        return self

    async def __aexit__(self, *_args):
        return None


class TInvestNormalizationTests(unittest.IsolatedAsyncioTestCase):
    def test_configures_official_sdk_ca_bundle(self):
        with patch.dict(os.environ, {}, clear=True):
            configure_t_invest_tls(True)
            self.assertEqual(os.environ["SSL_TBANK_VERIFY"], "true")

    def test_packs_spb_share_with_stable_identifiers(self):
        item = SimpleNamespace(
            uid="uid-aapl",
            figi="BBG000B9XRY4",
            ticker="aapl",
            isin="US0378331005",
            name="Apple",
            class_code="SPBXM",
            currency="usd",
            exchange="SPB",
            real_exchange=SimpleNamespace(name="REAL_EXCHANGE_SPB"),
            lot=1,
            api_trade_available_flag=True,
            buy_available_flag=True,
            sell_available_flag=True,
        )

        result = _pack_instrument(item, "share")

        self.assertEqual(result["secid"], "AAPL@SPBXM")
        self.assertEqual(result["uid"], "uid-aapl")
        self.assertEqual(result["currency"], "USD")
        self.assertEqual(result["exchange"], "SPB")

    async def test_converts_bond_percent_quote_to_money(self):
        instrument = {
            "uid": "bond-uid",
            "asset_type": "bond",
            "face_value": 1000.0,
        }
        price = LastPrice(
            instrument_uid="bond-uid",
            price=Quotation(units=98, nano=500_000_000),
            time=datetime(2026, 8, 27, 12, 0, tzinfo=UTC),
        )
        client = FakeClient([price])

        await _load_last_prices(client, [instrument])

        self.assertEqual(instrument["price_percent"], 98.5)
        self.assertEqual(instrument["last_price"], 985.0)
        self.assertEqual(instrument["price_source"], "t_invest")

    def test_reads_bond_nominal_from_sdk_money_value(self):
        item = SimpleNamespace(
            uid="bond-uid",
            figi="figi",
            ticker="bond",
            isin="RU0000000001",
            name="Bond",
            class_code="TQCB",
            currency="rub",
            exchange="MOEX",
            nominal=MoneyValue(currency="rub", units=1000, nano=0),
            lot=1,
        )

        result = _pack_instrument(item, "bond")

        self.assertEqual(result["face_value"], 1000.0)
        self.assertEqual(result["bond_name"], "Bond")

    def test_packs_neoasset_future_into_share_search_group(self):
        item = SimpleNamespace(
            uid="f8b9fd3f-96b0-43be-a4c2-73863b1bfee8",
            figi="NEO-NBIS-FIGI",
            ticker="NBISperpA",
            name="Neo Nebius",
            class_code="SPBFUT",
            currency="usd",
            exchange="SPB",
            basic_asset="NBIS",
            futures_type="perpetual",
            lot=1,
            api_trade_available_flag=True,
            buy_available_flag=True,
            sell_available_flag=True,
        )

        result = _pack_instrument(item, "neoasset")

        self.assertEqual(result["ticker"], "NBISPERPA")
        self.assertEqual(result["instrument_type"], "share")
        self.assertEqual(result["asset_type"], "neoasset")
        self.assertEqual(result["basic_asset"], "NBIS")
        self.assertIsNone(result["isin"])

    async def test_catalog_includes_only_perpetual_neoasset_futures(self):
        with patch("app.services.t_invest.AsyncClient", FakeCatalogClient):
            result = await get_broker_instruments("token")

        self.assertEqual([item["ticker"] for item in result], ["NBISPERPA"])
        self.assertEqual(result[0]["asset_type"], "neoasset")

    async def test_finds_neoasset_on_demand_with_supplied_user_token(self):
        FakeSearchClient.received_tokens.clear()
        with patch("app.services.t_invest.AsyncClient", FakeSearchClient):
            result = await find_broker_neoassets("NBISperpA", "user-token")

        self.assertEqual(FakeSearchClient.received_tokens, ["user-token"])
        self.assertEqual(result[0]["ticker"], "NBISPERPA")
        self.assertEqual(result[0]["currency"], "USD")

    async def test_live_enrichment_prefers_explicit_user_token(self):
        FakeSearchClient.received_tokens.clear()
        with patch("app.services.t_invest.AsyncClient", FakeSearchClient):
            result = await enrich_with_latest_prices(
                [{"uid": "neo-uid", "instrument_type": "share"}],
                token="stored-user-token",
            )

        self.assertEqual(FakeSearchClient.received_tokens, ["stored-user-token"])
        self.assertEqual(result[0]["uid"], "neo-uid")

    async def test_live_enrichment_falls_back_after_rejected_user_token(self):
        FakeFallbackClient.received_tokens.clear()
        rejected_user = MarketDataTokenCandidate(
            "rejected-user-token",
            "user",
        )
        system = MarketDataTokenCandidate("system-token", "system")
        on_unauthenticated = AsyncMock()

        with patch("app.services.t_invest.AsyncClient", FakeFallbackClient):
            result = await enrich_with_latest_prices(
                [{"uid": "resolved-uid", "instrument_type": "share"}],
                token_candidates=(rejected_user, system),
                on_unauthenticated=on_unauthenticated,
            )

        self.assertEqual(
            FakeFallbackClient.received_tokens,
            ["rejected-user-token", "system-token"],
        )
        on_unauthenticated.assert_awaited_once_with(rejected_user)
        self.assertEqual(result[0]["last_price"], 321.5)

    async def test_live_enrichment_resolves_moex_row_by_isin(self):
        FakeResolvingClient.received_tokens.clear()
        configure_market_data_token(None)
        with patch("app.services.t_invest.AsyncClient", FakeResolvingClient):
            result = await enrich_with_latest_prices(
                [
                    {
                        "secid": "SBER",
                        "isin": "RU0009029540",
                        "instrument_type": "share",
                        "last_price": 300.0,
                        "price_source": "trade",
                    }
                ],
                token="user-token",
            )

        self.assertEqual(FakeResolvingClient.received_tokens, ["user-token"])
        self.assertEqual(result[0]["uid"], "resolved-uid")
        self.assertEqual(result[0]["last_price"], 321.5)
        self.assertEqual(result[0]["price_source"], "t_invest")

    async def test_live_enrichment_replaces_stale_non_trading_uid(self):
        FakeResolvingClient.received_tokens.clear()
        configure_market_data_token(None)
        with patch("app.services.t_invest.AsyncClient", FakeResolvingClient):
            result = await enrich_with_latest_prices(
                [
                    {
                        "secid": "SBER",
                        "isin": "RU0009029540",
                        "uid": "stale-non-trading-uid",
                        "instrument_type": "share",
                        "last_price": 300.0,
                        "price_source": "trade",
                    }
                ],
                token="user-token",
            )

        self.assertEqual(result[0]["uid"], "resolved-uid")
        self.assertEqual(result[0]["last_price"], 321.5)
        self.assertEqual(result[0]["price_source"], "t_invest")


if __name__ == "__main__":
    unittest.main()
