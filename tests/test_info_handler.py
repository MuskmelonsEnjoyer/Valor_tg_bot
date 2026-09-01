import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.bot.handlers import INFO_PAGES, info_command, info_navigation


class InfoHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_info_command_opens_first_page(self):
        message = SimpleNamespace(answer=AsyncMock())

        await info_command(message)

        self.assertEqual(message.answer.await_args.args[0], INFO_PAGES[0])
        self.assertEqual(message.answer.await_args.kwargs["parse_mode"], "HTML")
        keyboard = message.answer.await_args.kwargs["reply_markup"]
        callbacks = {
            button.callback_data
            for row in keyboard.inline_keyboard
            for button in row
        }
        self.assertIn("info:1", callbacks)
        self.assertIn("get_bond_info", callbacks)

    async def test_page_callback_edits_the_existing_message(self):
        message = SimpleNamespace(edit_text=AsyncMock())
        callback = SimpleNamespace(
            data="info:1",
            answer=AsyncMock(),
            message=message,
        )

        await info_navigation(callback)

        callback.answer.assert_awaited_once_with()
        self.assertEqual(message.edit_text.await_args.args[0], INFO_PAGES[1])
        keyboard = message.edit_text.await_args.kwargs["reply_markup"]
        callbacks = {
            button.callback_data
            for row in keyboard.inline_keyboard
            for button in row
        }
        self.assertIn("info:0", callbacks)
        self.assertIn("info:2", callbacks)

    async def test_menu_callback_restores_main_reply_keyboard(self):
        message = SimpleNamespace(
            edit_reply_markup=AsyncMock(),
            answer=AsyncMock(),
        )
        callback = SimpleNamespace(
            data="info:menu",
            answer=AsyncMock(),
            message=message,
        )

        await info_navigation(callback)

        message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)
        self.assertEqual(message.answer.await_args.args[0], "Главное меню")
        reply_keyboard = message.answer.await_args.kwargs["reply_markup"]
        self.assertEqual(reply_keyboard.keyboard[0][0].text, "Облигации")

    async def test_invalid_page_shows_an_alert(self):
        callback = SimpleNamespace(
            data="info:99",
            answer=AsyncMock(),
            message=SimpleNamespace(edit_text=AsyncMock()),
        )

        await info_navigation(callback)

        callback.answer.assert_awaited_once_with(
            "Такой страницы нет", show_alert=True
        )
        callback.message.edit_text.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
