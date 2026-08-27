import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.bot.handlers import (
    _clear_state_preserving_valor_portfolio,
    portfolio_analysis_command,
    process_valor_temp_add,
    transfer_valor_temp_portfolio,
    valor_command,
)


class FakeState:
    def __init__(self, data=None):
        self.data = dict(data or {})
        self.state = None

    async def get_data(self):
        return dict(self.data)

    async def update_data(self, **kwargs):
        self.data.update(kwargs)
        return dict(self.data)

    async def set_state(self, state):
        self.state = state

    async def clear(self):
        self.data.clear()
        self.state = None


class PortfolioAnalysisHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_portfolio_analysis_button_returns_weighted_analytics(self):
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=42),
            answer=AsyncMock(),
        )
        portfolio = [
            {
                "instrument_type": "share",
                "secid": "SBER",
                "quantity": 2,
                "last_price": 100,
                "currency": "RUB",
            }
        ]
        profile = {
            ("share", "SBER"): {
                "inflation_risk": 2,
                "geopolitical_risk": 6,
                "domestic_political_risk": 2,
                "debt_risk": 3,
                "currency_risk": 4,
                "minority_shareholder_risk": 1,
            }
        }

        with (
            patch(
                "app.bot.handlers.requests.get_user_portfolio",
                AsyncMock(return_value=portfolio),
            ),
            patch(
                "app.bot.handlers.requests.get_user_token",
                AsyncMock(return_value=None),
            ) as get_token,
            patch(
                "app.bot.handlers.requests.get_valor_risk_profiles",
                AsyncMock(return_value=profile),
            ),
        ):
            await portfolio_analysis_command(message)

        text = message.answer.await_args.args[0]
        self.assertIn("риск-профиль портфеля", text)
        self.assertIn("Инфляция: <b>2.0/6</b>", text)
        self.assertEqual(message.answer.await_args.kwargs["parse_mode"], "HTML")
        get_token.assert_not_awaited()

    async def test_empty_portfolio_returns_instruction(self):
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=42),
            answer=AsyncMock(),
        )
        with patch(
            "app.bot.handlers.requests.get_user_portfolio",
            AsyncMock(return_value=[]),
        ):
            await portfolio_analysis_command(message)

        self.assertIn("портфель пока пуст", message.answer.await_args.args[0])


class ValorCatalogHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_navigation_preserves_only_temporary_portfolio(self):
        temporary = {"1": {"identifier": "SBER"}}
        state = FakeState(
            {
                "valor_temp_portfolio": temporary,
                "valor_pending_asset_id": 7,
                "valor_search_query": "Сбер",
            }
        )

        await _clear_state_preserving_valor_portfolio(state)

        self.assertEqual(state.data, {"valor_temp_portfolio": temporary})

    async def test_valor_button_opens_catalog_menu(self):
        message = SimpleNamespace(answer=AsyncMock())
        state = FakeState(
            {"valor_temp_portfolio": {"1": {"identifier": "SBER"}}}
        )

        await valor_command(message, state)

        text = message.answer.await_args.args[0]
        keyboard = message.answer.await_args.kwargs["reply_markup"]
        callbacks = [
            button.callback_data
            for row in keyboard.inline_keyboard
            for button in row
        ]
        self.assertIn("Подборка Valor", text)
        self.assertIn("valor_list:share:0", callbacks)
        self.assertIn("valor_temp_view", callbacks)
        self.assertIn("Временный портфель (1)", keyboard.inline_keyboard[2][0].text)

    async def test_position_is_saved_in_temporary_portfolio(self):
        message = SimpleNamespace(text="250.50 10", answer=AsyncMock())
        state = FakeState({"valor_pending_asset_id": 7})
        asset = {
            "id": 7,
            "asset_type": "share",
            "identifier": "SBER",
            "issuer": "Сбербанк",
            "currency": "RUB",
        }
        with patch(
            "app.bot.handlers.requests.get_valor_asset",
            AsyncMock(return_value=asset),
        ):
            await process_valor_temp_add(message, state)

        saved = state.data["valor_temp_portfolio"]["7"]
        self.assertEqual(saved["avg_price"], "250.50")
        self.assertEqual(saved["quantity"], 10)
        self.assertIsNone(state.state)

    async def test_transfer_keeps_only_unmatched_positions(self):
        state = FakeState(
            {
                "valor_temp_portfolio": {
                    "1": {
                        "asset_id": 1,
                        "asset_type": "share",
                        "identifier": "SBER",
                        "issuer": "Сбербанк",
                        "currency": "RUB",
                        "avg_price": "250.50",
                        "quantity": 10,
                    },
                    "2": {
                        "asset_id": 2,
                        "asset_type": "bond",
                        "identifier": "RU000A000000",
                        "issuer": "Тест",
                        "currency": "RUB",
                        "avg_price": "1000",
                        "quantity": 1,
                    },
                }
            }
        )
        callback = SimpleNamespace(
            from_user=SimpleNamespace(id=42),
            answer=AsyncMock(),
            message=SimpleNamespace(answer=AsyncMock()),
        )
        with patch(
            "app.bot.handlers.requests.upload_user_portfolio",
            AsyncMock(side_effect=[True, False]),
        ) as upload:
            await transfer_valor_temp_portfolio(callback, state)

        self.assertEqual(upload.await_count, 2)
        remaining = state.data["valor_temp_portfolio"]
        self.assertNotIn("1", remaining)
        self.assertIn("2", remaining)
        self.assertIn(
            "добавлено: <b>1</b>", callback.message.answer.await_args.args[0]
        )


if __name__ == "__main__":
    unittest.main()
