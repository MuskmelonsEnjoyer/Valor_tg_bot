import unittest

from app.bot.keyboard import (
    get_add_to_portfolio_keyboard,
    get_instrument_search_keyboard,
    get_portfolio_reply_keyboard,
    get_valor_assets_keyboard,
    get_valor_menu_keyboard,
    get_valor_temp_portfolio_keyboard,
    info_keyboard,
)


class InstrumentKeyboardTests(unittest.IsolatedAsyncioTestCase):
    async def test_info_keyboard_has_inline_navigation_and_section_action(self):
        keyboard = await info_keyboard(page=1, total_pages=3)
        callbacks = {
            button.callback_data
            for row in keyboard.inline_keyboard
            for button in row
        }

        self.assertIn("valor_menu", callbacks)
        self.assertIn("info:0", callbacks)
        self.assertIn("info:2", callbacks)
        self.assertIn("info:menu", callbacks)

    async def test_result_and_pagination_callbacks_are_compact(self):
        keyboard = await get_instrument_search_keyboard(
            [
                {
                    "name": "Сбербанк",
                    "secid": "SBER",
                    "isin": "RU0009029540",
                }
            ],
            page=0,
            has_next=True,
        )

        callbacks = [
            button.callback_data
            for row in keyboard.inline_keyboard
            for button in row
            if button.callback_data
        ]
        self.assertIn("instrument_select:SBER", callbacks)
        self.assertIn("instrument_page:1", callbacks)
        self.assertLessEqual(max(map(len, callbacks)), 64)

    async def test_add_callback_contains_only_secid(self):
        keyboard = await get_add_to_portfolio_keyboard("SBER")
        button = keyboard.inline_keyboard[0][0]
        self.assertEqual(button.callback_data, "portfolio_add:SBER")
        self.assertLessEqual(len(button.callback_data), 64)

    async def test_portfolio_keyboard_contains_analysis_button(self):
        keyboard = await get_portfolio_reply_keyboard()
        labels = {
            button.text
            for row in keyboard.keyboard
            for button in row
        }

        self.assertIn("Анализ моего портфеля", labels)

    async def test_valor_menu_contains_catalog_and_temp_portfolio(self):
        keyboard = await get_valor_menu_keyboard(temp_count=3)
        callbacks = {
            button.callback_data
            for row in keyboard.inline_keyboard
            for button in row
        }

        self.assertIn("valor_list:share:0", callbacks)
        self.assertIn("valor_list:bond:0", callbacks)
        self.assertIn("valor_search", callbacks)
        self.assertIn("valor_temp_view", callbacks)
        self.assertIn("(3)", keyboard.inline_keyboard[2][0].text)

    async def test_valor_catalog_pagination_callbacks_are_compact(self):
        keyboard = await get_valor_assets_keyboard(
            [{"id": 12, "issuer": "Сбербанк", "identifier": "SBER"}],
            page=1,
            has_next=True,
            asset_type="share",
        )
        callbacks = [
            button.callback_data
            for row in keyboard.inline_keyboard
            for button in row
        ]

        self.assertIn("valor_asset:12", callbacks)
        self.assertIn("valor_list:share:0", callbacks)
        self.assertIn("valor_list:share:2", callbacks)
        self.assertLessEqual(max(map(len, callbacks)), 64)

    async def test_temporary_portfolio_has_pagination_and_transfer(self):
        items = [
            {"asset_id": index, "identifier": f"TEST{index}"}
            for index in range(10)
        ]
        keyboard = await get_valor_temp_portfolio_keyboard(items, page=1)
        callbacks = [
            button.callback_data
            for row in keyboard.inline_keyboard
            for button in row
        ]

        self.assertIn("valor_temp_view:0", callbacks)
        self.assertIn("valor_temp_remove:8:1", callbacks)
        self.assertIn("valor_temp_transfer", callbacks)
