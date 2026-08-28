import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from grpc import StatusCode
from t_tech.invest.exceptions import AioUnauthenticatedError

from app.bot.handlers import sync_portfolio_by_token
from app.services.t_invest import MarketDataTokenCandidate
from app.services.t_invest_token import (
    discard_rejected_user_token,
    find_broker_neoassets_for_user,
    resolve_market_data_token,
    resolve_market_data_tokens,
)


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
        get_system_token.assert_called_once_with()

    async def test_returns_user_then_system_candidates(self):
        with (
            patch(
                "app.services.t_invest_token.requests.get_user_token",
                new=AsyncMock(return_value=" user-token "),
            ),
            patch(
                "app.services.t_invest_token.get_market_data_token",
                return_value=" system-token ",
            ),
        ):
            candidates = await resolve_market_data_tokens(42)

        self.assertEqual(
            candidates,
            (
                MarketDataTokenCandidate("user-token", "user"),
                MarketDataTokenCandidate("system-token", "system"),
            ),
        )

    async def test_deduplicates_same_user_and_system_token(self):
        with (
            patch(
                "app.services.t_invest_token.requests.get_user_token",
                new=AsyncMock(return_value="same-token"),
            ),
            patch(
                "app.services.t_invest_token.get_market_data_token",
                return_value="same-token",
            ),
        ):
            candidates = await resolve_market_data_tokens(42)

        self.assertEqual(
            candidates,
            (MarketDataTokenCandidate("same-token", "user"),),
        )

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

    async def test_rejected_user_token_is_deleted_only_if_unchanged(self):
        rejected = MarketDataTokenCandidate("rejected-token", "user")
        with (
            patch(
                "app.services.t_invest_token.requests.get_user_token",
                new=AsyncMock(return_value="new-token"),
            ),
            patch(
                "app.services.t_invest_token.requests.delete_user_token",
                new=AsyncMock(return_value=True),
            ) as delete_token,
        ):
            deleted = await discard_rejected_user_token(42, rejected)

        self.assertFalse(deleted)
        delete_token.assert_not_awaited()

    async def test_neoasset_search_falls_back_after_rejected_user_token(self):
        rejected = AioUnauthenticatedError(
            StatusCode.UNAUTHENTICATED,
            "40003",
            None,
        )
        broker_row = {"ticker": "NBISPERPA", "uid": "neo-uid"}
        with (
            patch(
                "app.services.t_invest_token.requests.get_user_token",
                new=AsyncMock(side_effect=["user-token", "user-token"]),
            ),
            patch(
                "app.services.t_invest_token.requests.delete_user_token",
                new=AsyncMock(return_value=True),
            ) as delete_token,
            patch(
                "app.services.t_invest_token.get_market_data_token",
                return_value="system-token",
            ),
            patch(
                "app.services.t_invest_token.find_broker_neoassets",
                new=AsyncMock(side_effect=[rejected, [broker_row]]),
            ) as search,
        ):
            result = await find_broker_neoassets_for_user("NBISperpA", 42)

        self.assertEqual(result, [broker_row])
        self.assertEqual(
            [call.args[1] for call in search.await_args_list],
            ["user-token", "system-token"],
        )
        delete_token.assert_awaited_once_with(42)

    async def test_private_portfolio_does_not_use_system_token(self):
        message = SimpleNamespace(answer=AsyncMock())
        with (
            patch(
                "app.bot.handlers.resolve_private_user_token",
                new=AsyncMock(return_value=None),
            ) as get_private_token,
            patch(
                "app.bot.handlers.portfolio_service.get_user_portfolio_token",
                new=AsyncMock(),
            ) as load_portfolio,
        ):
            await sync_portfolio_by_token(message, 42)

        get_private_token.assert_awaited_once_with(42)
        load_portfolio.assert_not_awaited()
        self.assertIn("привязать свой токен", message.answer.await_args.args[0])

    async def test_rejected_private_token_is_removed_without_system_fallback(self):
        message = SimpleNamespace(answer=AsyncMock())
        rejected = AioUnauthenticatedError(
            StatusCode.UNAUTHENTICATED,
            "40003",
            None,
        )
        with (
            patch(
                "app.bot.handlers.resolve_private_user_token",
                new=AsyncMock(return_value="rejected-token"),
            ),
            patch(
                "app.bot.handlers.portfolio_service.get_user_portfolio_token",
                new=AsyncMock(side_effect=rejected),
            ),
            patch(
                "app.bot.handlers.discard_rejected_private_user_token",
                new=AsyncMock(return_value=True),
            ) as discard_token,
        ):
            await sync_portfolio_by_token(message, 42)

        discard_token.assert_awaited_once_with(42, "rejected-token")
        self.assertIn("был удален", message.answer.await_args.args[0])
        self.assertIn("/set_token", message.answer.await_args.args[0])


if __name__ == "__main__":
    unittest.main()
