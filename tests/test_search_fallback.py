import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.bot.handlers import _show_instrument_results, select_instrument


class UserTokenSearchFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_selected_instrument_is_sent_before_live_update(self):
        state = AsyncMock()
        card_message = SimpleNamespace(edit_text=AsyncMock())
        callback = SimpleNamespace(
            data="instrument_select:SBER",
            answer=AsyncMock(),
            from_user=SimpleNamespace(id=123),
            message=SimpleNamespace(answer=AsyncMock(return_value=card_message)),
        )
        stored = {
            "secid": "SBER",
            "isin": "RU0009029540",
            "name": "Сбербанк",
            "instrument_type": "share",
            "currency": "RUB",
            "last": 300.0,
            "price_source": "trade",
        }
        enriched = dict(
            stored,
            uid="resolved-uid",
            last=321.5,
            last_price=321.5,
            price_source="t_invest",
        )

        with (
            patch(
                "app.bot.handlers.requests.get_instrument_info",
                new=AsyncMock(return_value=stored),
            ),
            patch(
                "app.bot.handlers.refresh_and_store_instrument",
                new=AsyncMock(return_value=enriched),
            ) as refresh,
            patch(
                "app.bot.handlers.keyboards.get_add_to_portfolio_keyboard",
                new=AsyncMock(return_value=None),
            ),
        ):
            await select_instrument(callback, state)

        cached_text = callback.message.answer.await_args.args[0]
        live_text = card_message.edit_text.await_args.args[0]
        self.assertIn("MOEX", cached_text)
        self.assertIn("T-Invest", live_text)
        refresh.assert_awaited_once_with(stored, user_id=123)
        state.clear.assert_not_awaited()

    async def test_search_session_allows_multiple_instrument_selections(self):
        state = AsyncMock()
        first_card = SimpleNamespace(edit_text=AsyncMock())
        second_card = SimpleNamespace(edit_text=AsyncMock())
        message = SimpleNamespace(
            answer=AsyncMock(side_effect=[first_card, second_card])
        )
        callback = SimpleNamespace(
            data="instrument_select:SBER",
            answer=AsyncMock(),
            from_user=SimpleNamespace(id=123),
            message=message,
        )
        sber = {
            "secid": "SBER",
            "name": "Сбербанк",
            "instrument_type": "share",
            "last": 300.0,
            "price_source": "trade",
        }
        lkoh = {
            "secid": "LKOH",
            "name": "Лукойл",
            "instrument_type": "share",
            "last": 7000.0,
            "price_source": "trade",
        }

        with (
            patch(
                "app.bot.handlers.requests.get_instrument_info",
                new=AsyncMock(side_effect=[sber, lkoh]),
            ) as get_instrument,
            patch(
                "app.bot.handlers.refresh_and_store_instrument",
                new=AsyncMock(side_effect=[sber, lkoh]),
            ),
            patch(
                "app.bot.handlers.keyboards.get_add_to_portfolio_keyboard",
                new=AsyncMock(return_value=None),
            ),
        ):
            await select_instrument(callback, state)
            callback.data = "instrument_select:LKOH"
            await select_instrument(callback, state)

        self.assertEqual(
            [call.args[0] for call in get_instrument.await_args_list],
            ["SBER", "LKOH"],
        )
        self.assertEqual(message.answer.await_count, 2)
        state.clear.assert_not_awaited()

    async def test_existing_results_are_available_during_background_refresh(self):
        state = AsyncMock()
        state.get_data.return_value = {"instrument_type": "share"}
        message = SimpleNamespace(answer=AsyncMock())
        stored_row = {
            "secid": "SBER",
            "name": "Сбербанк",
            "instrument_type": "share",
        }

        with (
            patch("app.bot.handlers.catalog_is_ready", return_value=False),
            patch(
                "app.bot.handlers.requests.search_instruments",
                new=AsyncMock(return_value=([stored_row], False)),
            ),
            patch(
                "app.bot.handlers.keyboards.get_instrument_search_keyboard",
                new=AsyncMock(return_value=None),
            ),
        ):
            await _show_instrument_results(message, state, "SBER")

        self.assertIn("SBER", str(message.answer.await_args))

    async def test_missing_neoasset_is_imported_then_read_from_database(self):
        state = AsyncMock()
        state.get_data.return_value = {
            "instrument_type": "share",
            "search_user_id": 123,
        }
        message = SimpleNamespace(answer=AsyncMock())
        stored_row = {
            "secid": "NBISPERPA@SPBFUT",
            "ticker": "NBISPERPA",
            "name": "Neo Nebius",
            "instrument_type": "share",
            "asset_type": "neoasset",
        }
        broker_row = dict(stored_row, uid="neo-uid")

        with (
            patch("app.bot.handlers.catalog_is_ready", return_value=True),
            patch(
                "app.bot.handlers.requests.search_instruments",
                new=AsyncMock(side_effect=[([], False), ([stored_row], False)]),
            ) as search,
            patch(
                "app.bot.handlers.find_broker_neoassets_for_user",
                new=AsyncMock(return_value=[broker_row]),
            ) as find_neoassets,
            patch(
                "app.bot.handlers.requests.upsert_instrument_catalog",
                new=AsyncMock(return_value=1),
            ) as upsert,
            patch(
                "app.bot.handlers.keyboards.get_instrument_search_keyboard",
                new=AsyncMock(return_value=None),
            ),
        ):
            await _show_instrument_results(message, state, "NBISperpA")

        find_neoassets.assert_awaited_once_with("NBISperpA", 123)
        upsert.assert_awaited_once_with([broker_row])
        self.assertEqual(search.await_count, 2)
        self.assertIn("NBISperpA", str(message.answer.await_args))


if __name__ == "__main__":
    unittest.main()
