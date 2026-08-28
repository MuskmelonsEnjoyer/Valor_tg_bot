import unittest

import main
from app.bot.handlers import ClearStateOnCommandMiddleware, router
from app.database.models import Base


class ApplicationSmokeTests(unittest.TestCase):
    def test_runtime_modules_import_without_starting_polling(self):
        self.assertTrue(callable(main.main))
        self.assertGreater(len(router.message.handlers), 0)
        self.assertEqual(
            {table.name for table in Base.metadata.tables.values()},
            {
                "app_users",
                "instruments",
                "users_t_invest_tokens",
                "user_portfolio",
                "bonds",
                "valor_asset_risks",
            },
        )


class FakeState:
    def __init__(self):
        self.cleared = False

    async def clear(self):
        self.cleared = True


class FakeMessage:
    def __init__(self, text: str):
        self.text = text


class CommandMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def test_command_clears_state_before_handler(self):
        state = FakeState()
        state_seen_by_handler = None
        raw_state_seen_by_handler = "unset"

        async def handler(event, data):
            nonlocal state_seen_by_handler, raw_state_seen_by_handler
            state_seen_by_handler = data["state"].cleared
            raw_state_seen_by_handler = data["raw_state"]
            return "handled"

        result = await ClearStateOnCommandMiddleware()(
            handler,
            FakeMessage("/policy"),
            {"state": state, "raw_state": "UserState:waiting_for_token"},
        )

        self.assertEqual(result, "handled")
        self.assertTrue(state_seen_by_handler)
        self.assertIsNone(raw_state_seen_by_handler)

    async def test_menu_action_clears_state_before_handler(self):
        state = FakeState()

        async def handler(_event, data):
            return data["state"].cleared, data["raw_state"]

        result = await ClearStateOnCommandMiddleware()(
            handler,
            FakeMessage("Мой портфель"),
            {"state": state, "raw_state": "UserState:search_instrument"},
        )

        self.assertEqual(result, (True, None))

    async def test_search_query_keeps_current_state(self):
        state = FakeState()

        async def handler(_event, data):
            return data["state"].cleared, data["raw_state"]

        result = await ClearStateOnCommandMiddleware()(
            handler,
            FakeMessage("Сбербанк"),
            {"state": state, "raw_state": "UserState:search_instrument"},
        )

        self.assertEqual(result, (False, "UserState:search_instrument"))
