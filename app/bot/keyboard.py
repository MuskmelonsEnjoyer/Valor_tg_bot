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
<<<<<<< HEAD
=======
            [KeyboardButton(text="Анализ моего портфеля")],
>>>>>>> f04103d (version 1.0.0)
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
<<<<<<< HEAD
            [InlineKeyboardButton(text="Загрузить портфель из файла", callback_data="get_portfolio_xlx")],
=======
>>>>>>> f04103d (version 1.0.0)
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
<<<<<<< HEAD
    return keyboard
=======
    return keyboard


async def get_valor_menu_keyboard(temp_count: int = 0) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📈 Акции", callback_data="valor_list:share:0"
                ),
                InlineKeyboardButton(
                    text="📄 Облигации", callback_data="valor_list:bond:0"
                ),
            ],
            [InlineKeyboardButton(text="🔎 Поиск бумаги", callback_data="valor_search")],
            [
                InlineKeyboardButton(
                    text=f"🧺 Временный портфель ({temp_count})",
                    callback_data="valor_temp_view",
                )
            ],
        ]
    )


async def get_valor_assets_keyboard(
    assets: list[dict],
    *,
    page: int,
    has_next: bool,
    asset_type: str | None = None,
    is_search: bool = False,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f'{asset.get("issuer", "Без названия")[:32]} ({asset["identifier"]})',
                callback_data=f'valor_asset:{asset["id"]}',
            )
        ]
        for asset in assets
    ]
    navigation = []
    if page > 0:
        callback_data = (
            f"valor_search_page:{page - 1}"
            if is_search
            else f"valor_list:{asset_type}:{page - 1}"
        )
        navigation.append(InlineKeyboardButton(text="Назад", callback_data=callback_data))
    if has_next:
        callback_data = (
            f"valor_search_page:{page + 1}"
            if is_search
            else f"valor_list:{asset_type}:{page + 1}"
        )
        navigation.append(InlineKeyboardButton(text="Далее", callback_data=callback_data))
    if navigation:
        rows.append(navigation)
    rows.append([InlineKeyboardButton(text="В меню Valor", callback_data="valor_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def get_valor_asset_keyboard(asset_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Во временный портфель",
                    callback_data=f"valor_temp_add:{asset_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🧺 Временный портфель", callback_data="valor_temp_view"
                )
            ],
            [InlineKeyboardButton(text="В меню Valor", callback_data="valor_menu")],
        ]
    )


async def get_valor_temp_portfolio_keyboard(
    items: list[dict],
    *,
    page: int = 0,
    page_size: int = 8,
) -> InlineKeyboardMarkup:
    max_page = max(0, (len(items) - 1) // page_size)
    page = max(0, min(page, max_page))
    visible_items = items[page * page_size : (page + 1) * page_size]
    rows = [
        [
            InlineKeyboardButton(
                text=f'❌ {item["identifier"]}',
                callback_data=f'valor_temp_remove:{item["asset_id"]}:{page}',
            )
        ]
        for item in visible_items
    ]
    navigation = []
    if page > 0:
        navigation.append(
            InlineKeyboardButton(
                text="Назад", callback_data=f"valor_temp_view:{page - 1}"
            )
        )
    if page < max_page:
        navigation.append(
            InlineKeyboardButton(
                text="Далее", callback_data=f"valor_temp_view:{page + 1}"
            )
        )
    if navigation:
        rows.append(navigation)
    if items:
        rows.extend(
            [
                [
                    InlineKeyboardButton(
                        text="✅ Добавить всё в основной портфель",
                        callback_data="valor_temp_transfer",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🗑 Очистить временный портфель",
                        callback_data="valor_temp_clear",
                    )
                ],
            ]
        )
    rows.append([InlineKeyboardButton(text="В меню Valor", callback_data="valor_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def get_instrument_search_keyboard(
    instruments: list[dict], page: int, has_next: bool
) -> InlineKeyboardMarkup:
    rows = []
    for instrument in instruments:
        name = instrument.get("name") or instrument.get("bond_name") or "Без названия"
        secid = instrument["secid"]
        isin = instrument.get("isin") or "без ISIN"
        label = f"{name[:38]} ({secid})"
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"instrument_select:{secid}",
                )
            ]
        )

    navigation = []
    if page > 0:
        navigation.append(
            InlineKeyboardButton(
                text="Назад", callback_data=f"instrument_page:{page - 1}"
            )
        )
    if has_next:
        navigation.append(
            InlineKeyboardButton(
                text="Далее", callback_data=f"instrument_page:{page + 1}"
            )
        )
    if navigation:
        rows.append(navigation)
    rows.append(
        [InlineKeyboardButton(text="Отмена", callback_data="instrument_cancel")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def get_add_to_portfolio_keyboard(secid: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Добавить в портфель",
                    callback_data=f"portfolio_add:{secid}",
                )
            ]
        ]
    )
>>>>>>> f04103d (version 1.0.0)
