from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)


# Клавиатура главного меню
async def get_reply_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Облигации"), KeyboardButton(text="Акции и фонды")],
            [KeyboardButton(text="Подборка Valor")],
            [KeyboardButton(text="Портфель")],
        ],
        resize_keyboard = True
    )

    return keyboard

# Клавиатура портфеля
async def get_portfolio_reply_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Мой портфель")],
            [KeyboardButton(text="Добавить актив"), KeyboardButton(text="Удалить актив")],
            [KeyboardButton(text="Назад в меню")]
        ],
        resize_keyboard = True
    )

    return keyboard


# Инлайн клавиатура облигаций
async def get_inline_keybord_bonds():
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Получить информацию по облигации", callback_data="get_bond_info")]
        ]
    )

    return keyboard


# Инлайн клавиатура акций и облигаций
async def get_inline_keybord_shares_etfs():
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Получить информацию по акции или ETF", callback_data="get_share_etf_info")]
        ]
    )

    return keyboard


# Инлайн клавитаруа добавления актива в портфель
async def get_inline_keybord_portfolio_add_paper():
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Добавить бумагу по ISIN", callback_data="add_paper_isin")],
            [InlineKeyboardButton(text="Загрузить портфель из файла", callback_data="get_portfolio_xlx")],
            [InlineKeyboardButton(text="Загрузить портфель по API токену", callback_data="get_portfolio_token")]
        ]
    )

    return keyboard


# Инлайн клавиатура удаления актива из портфеля
async def get_inline_keybord_portfolio_delete_paper():
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Удалить бумагу по ISIN", callback_data="delete_paper_by_isin")],
            [InlineKeyboardButton(text="Удалить портфель", callback_data="delete_portfolio")]
        ]
    )

    return keyboard


async def get_agreement_keyboard():
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Да", callback_data="yes")],
            [InlineKeyboardButton(text="Нет", callback_data="no")]
        ]
    )
    return keyboard