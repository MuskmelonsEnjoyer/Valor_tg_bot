import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.bot.handlers import (
    _display_currency,
    _format_instrument_card,
    _instrument_price_currency,
    _portfolio_open,
    _portfolio_price,
    process_bond_info,
    process_share_etf_info,
    send_table_tg,
)


class PortfolioDisplayTests(unittest.TestCase):
    def test_normalizes_currency_codes_for_display(self):
        self.assertEqual(_display_currency("rub"), "RUB")
        self.assertEqual(_display_currency("RUR"), "RUB")
        self.assertEqual(_display_currency("SUR"), "RUB")
        self.assertEqual(_display_currency("usd"), "USD")

    def test_t_invest_price_uses_instrument_currency_for_bond(self):
        paper = {
            "instrument_type": "bond",
            "price_source": "t_invest",
            "currency": "usd",
            "faceunit": "SUR",
        }

        self.assertEqual(_instrument_price_currency(paper), "USD")

    def test_moex_bond_price_uses_nominal_currency(self):
        paper = {
            "instrument_type": "bond",
            "price_source": "trade",
            "currency": "USD",
            "faceunit": "SUR",
        }

        self.assertEqual(_instrument_price_currency(paper), "RUB")

    def test_uses_normalized_share_price(self):
        paper = {"last_price": "123.45", "last": "122.00"}

        self.assertEqual(_portfolio_price(paper, "share"), 123.45)

    def test_converts_legacy_bond_percentage_to_money(self):
        paper = {"last": "98.5", "face_value": "1000"}

        self.assertEqual(_portfolio_price(paper, "bond"), 985.0)

    def test_prefers_normalized_bond_price_over_percentage(self):
        paper = {
            "last_price": "985.00",
            "price_percent": "98.5",
            "face_value": "1000",
        }

        self.assertEqual(_portfolio_price(paper, "bond"), 985.0)

    def test_does_not_calculate_delta_from_previous_reference(self):
        paper = {
            "last_price": 985.0,
            "open": 990.0,
            "price_source": "previous_reference",
        }

        self.assertIsNone(_portfolio_open(paper, "bond"))

    def test_converts_legacy_bond_open_percentage(self):
        paper = {"open": 99.0, "face_value": 1000}

        self.assertEqual(_portfolio_open(paper, "bond"), 990.0)

    def test_invalid_price_is_missing(self):
        paper = {"last_price": "not-a-price", "last": None}

        self.assertIsNone(_portfolio_price(paper, "share"))

    def test_incomplete_bond_card_shows_missing_values(self):
        text = _format_instrument_card(
            {
                "instrument_type": "bond",
                "bond_name": "Test bond",
                "secid": "TEST",
                "isin": "RU0000000000",
                "currency": "RUB",
                "coupon_percent": 5,
            }
        )

        self.assertIn("Купон:</b> 5.00%", text)
        self.assertIn("YLT:</b> Н/Д", text)
        self.assertIn("Источник:", text)

    def test_neoasset_card_has_its_own_type(self):
        text = _format_instrument_card(
            {
                "instrument_type": "share",
                "asset_type": "neoasset",
                "name": "Neo Nebius",
                "secid": "NBISPERPA@SPBFUT",
                "currency": "usd",
                "last": 212.23,
                "price_source": "t_invest",
            }
        )

        self.assertIn("Тип:</b> Неоактив", text)
        self.assertIn("212.23 USD", text)

    def test_t_invest_card_does_not_show_trade_timestamp(self):
        text = _format_instrument_card(
            {
                "instrument_type": "share",
                "name": "Сбербанк",
                "secid": "SBER",
                "currency": "RUB",
                "last": 321.5,
                "price_source": "t_invest",
                "price_date": "2026-08-27T12:00:00+00:00",
            }
        )

        self.assertIn("T-Invest, цена последней сделки", text)
        self.assertNotIn("2026-08-27", text)


class PortfolioDisplayHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_share_price_from_t_invest_includes_currency(self):
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=42),
            text="AAPL",
            answer=AsyncMock(),
        )
        state = SimpleNamespace(clear=AsyncMock())
        instrument = {
            "instrument_type": "share",
            "name": "Apple",
            "secid": "AAPL",
            "last": 229.35,
            "currency": "usd",
            "price_source": "t_invest",
        }

        with (
            patch(
                "app.bot.handlers.requests.get_share_etf_info",
                new=AsyncMock(return_value=dict(instrument)),
            ),
            patch(
                "app.bot.handlers.resolve_market_data_token",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.bot.handlers.refresh_and_store_instrument",
                new=AsyncMock(return_value=instrument),
            ),
        ):
            await process_share_etf_info(message, state)

        text = message.answer.await_args.args[0]
        self.assertIn("229.35 USD", text)

    async def test_bond_price_from_t_invest_uses_instrument_currency(self):
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=42),
            text="US0000000001",
            answer=AsyncMock(),
        )
        state = SimpleNamespace(clear=AsyncMock())
        instrument = {
            "instrument_type": "bond",
            "bond_name": "Test USD bond",
            "isin": "US0000000001",
            "last_price": 995.5,
            "currency": "usd",
            "faceunit": "SUR",
            "price_source": "t_invest",
            "face_value": 1000,
            "coupon_value": 25,
            "coupon_percent": 5,
            "coupon_period": 182,
            "accruedint": 12.5,
        }

        with (
            patch(
                "app.bot.handlers.requests.get_bonds_info",
                new=AsyncMock(return_value=dict(instrument)),
            ),
            patch(
                "app.bot.handlers.resolve_market_data_token",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.bot.handlers.refresh_and_store_instrument",
                new=AsyncMock(return_value=instrument),
            ),
        ):
            await process_bond_info(message, state)

        text = message.answer.await_args.args[0]
        self.assertIn("Текущая цена:</b> 995.50 USD", text)
        self.assertIn("НКД:</b> 12.50 USD", text)

    async def test_reads_local_portfolio_without_user_token_request(self):
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=42),
            chat=SimpleNamespace(id=42),
            bot=SimpleNamespace(send_rich_message=AsyncMock()),
            answer=AsyncMock(),
        )
        portfolio = [
            {
                "instrument_type": "share",
                "name": "Сбербанк",
                "quantity": 2,
                "last_price": 321.5,
                "currency": "RUB",
                "price_source": "t_invest",
            }
        ]

        with (
            patch(
                "app.bot.handlers.requests.get_user_portfolio",
                new=AsyncMock(return_value=portfolio),
            ) as get_portfolio,
            patch(
                "app.bot.handlers.requests.get_user_token",
                new=AsyncMock(return_value="must-not-be-read"),
            ) as get_token,
        ):
            await send_table_tg(message)

        get_portfolio.assert_awaited_once_with(42)
        get_token.assert_not_awaited()
        message.bot.send_rich_message.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
