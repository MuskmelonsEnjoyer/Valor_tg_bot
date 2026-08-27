import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.bot.handlers import sync_portfolio_by_token
from app.services.t_invest_token import resolve_market_data_token


class TInvestTokenResolutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_prefers_user_token(self):
        with (
            patch(
                "app.services.t_invest_token.requests.get_user_token",
                new=AsyncMock(return_value=" user-token "),
            ) as get_user_token,
            patch(
                "app.services.t_invest_token.get_market_data_token",
                return_value="system-token",
            ) as get_system_token,
        ):
            token = await resolve_market_data_token(42)

        self.assertEqual(token, "user-token")
        get_user_token.assert_awaited_once_with(42)
        get_system_token.assert_not_called()

    async def test_uses_system_token_when_user_has_none(self):
        with (
            patch(
                "app.services.t_invest_token.requests.get_user_token",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.services.t_invest_token.get_market_data_token",
                return_value=" system-token ",
            ),
        ):
            token = await resolve_market_data_token(42)

        self.assertEqual(token, "system-token")

    async def test_returns_none_when_no_token_is_available(self):
        with (
            patch(
                "app.services.t_invest_token.requests.get_user_token",
                new=AsyncMock(return_value=" "),
            ),
            patch(
                "app.services.t_invest_token.get_market_data_token",
                return_value=None,
            ),
        ):
            token = await resolve_market_data_token(42)

        self.assertIsNone(token)

    async def test_private_portfolio_does_not_use_system_token(self):
        message = SimpleNamespace(answer=AsyncMock())
        with (
            patch(
                "app.bot.handlers.requests.get_user_token",
                new=AsyncMock(return_value=None),
            ) as get_user_token,
            patch(
                "app.bot.handlers.portfolio_service.get_user_portfolio_token",
                new=AsyncMock(),
            ) as load_portfolio,
            patch(
                "app.bot.handlers.resolve_market_data_token",
                new=AsyncMock(return_value="system-token"),
            ) as resolve_public_token,
        ):
            await sync_portfolio_by_token(message, 42)

        get_user_token.assert_awaited_once_with(42)
        load_portfolio.assert_not_awaited()
        resolve_public_token.assert_not_awaited()
        self.assertIn("привязать свой токен", message.answer.await_args.args[0])


if __name__ == "__main__":
    unittest.main()
