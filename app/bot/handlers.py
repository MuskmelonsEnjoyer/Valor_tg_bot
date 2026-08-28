import logging
from decimal import Decimal, InvalidOperation
from math import isfinite
from typing import Any, Awaitable, Callable

import app.bot.keyboard as keyboards
import app.services.portfolio_service as portfolio_service
from app.services.valor_analytics import (
    calculate_portfolio_risks,
    format_portfolio_risks,
    format_valor_asset_profile,
)
from app.services.instrument_refresh import catalog_is_ready
from app.services.instrument_price_service import refresh_and_store_instrument
from app.services.t_invest_token import (
    discard_rejected_private_user_token,
    find_broker_neoassets_for_user,
    resolve_private_user_token,
)
from aiogram import BaseMiddleware, Bot, F, Router, html
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BotCommand,
    BotCommandScopeDefault,
    CallbackQuery,
    InputRichBlockTable,
    InputRichMessage,
    Message,
    RichBlockTableCell,
)
from app.bot import states
from app.database import requests
from app.utils import formatting
from t_tech.invest import AioRequestError, AsyncClient

router = Router()
logger = logging.getLogger("handlers")
MENU_BUTTONS = {
    "облигации",
    "акции и фонды",
    "подборка valor",
    "портфель",
    "мой портфель",
    "анализ моего портфеля",
    "добавить актив",
    "удалить актив",
    "назад в меню",
}


class ClearStateOnCommandMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        normalized_text = event.text.strip().lower() if event.text else ""
        if normalized_text.startswith("/") or normalized_text in MENU_BUTTONS:
            state = data.get("state")
            if state is not None:
                await state.clear()
                data["raw_state"] = None
        return await handler(event, data)


router.message.outer_middleware(ClearStateOnCommandMiddleware())


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _display_currency(value: Any, *, default: str = "RUB") -> str:
    """Return a consistent, user-facing currency code."""
    currency = str(value or default).strip().upper()
    if currency in {"RUB", "RUR", "SUR"}:
        return "RUB"
    return currency


def _instrument_price_currency(
    instrument: dict[str, Any],
    instrument_type: str | None = None,
    *,
    default: str = "RUB",
) -> str:
    """Choose the currency that corresponds to the displayed price."""
    instrument_type = instrument_type or instrument.get("instrument_type")
    currency = instrument.get("currency")
    faceunit = instrument.get("faceunit")

    # T-Invest returns a monetary price in the instrument currency. MOEX bond
    # records may instead describe their quote through the nominal currency.
    if instrument_type == "bond" and instrument.get("price_source") != "t_invest":
        currency = faceunit or currency
    else:
        currency = currency or faceunit

    return _display_currency(currency, default=default)


def _portfolio_price(paper: dict[str, Any], instrument_type: str) -> float | None:
    """Return the portfolio price in money units, not an MOEX bond percentage."""
    price = _safe_float(paper.get("last_price"))
    if price is not None:
        return price

    if instrument_type == "bond":
        percent = _safe_float(paper.get("price_percent"))
        if percent is None:
            # Older records only have MOEX's percentage quote in ``last``.
            percent = _safe_float(paper.get("last"))
        face_value = _safe_float(paper.get("face_value"))
        if percent is not None and face_value is not None:
            return percent * face_value / 100

    return _safe_float(paper.get("last"))


def _portfolio_open(paper: dict[str, Any], instrument_type: str) -> float | None:
    if paper.get("price_source") in {"previous_close", "previous_reference"}:
        return None

    opening_price = _safe_float(paper.get("open"))
    if opening_price is None:
        return None

    # Before prices were normalized, bond ``open`` was also stored as a
    # percentage of the nominal value.
    if instrument_type == "bond" and "price_percent" not in paper:
        face_value = _safe_float(paper.get("face_value"))
        if face_value is not None:
            return opening_price * face_value / 100

    return opening_price


# обработчик команды /start
@router.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    await message.answer(
        f"Привет, {html.bold(message.from_user.full_name)}!\n"
        "Это бот команды <b>Valor</b>.\n" \
        "Наша цель — помочь новичкам освоиться на фондовом рынке.\n\n"
        "<b>Чем бот может быть полезен?</b>\n" \
        "• Найти информацию по облигациям, акциям и фондам вручную\n"
        "• Собрать портфель\n"
        "• Изучить готовую аналитику от наших экспертов в разделе:\n"
        "<b><i>«Подборка Valor»</i></b>\n\n",
        parse_mode="HTML",
        reply_markup=await keyboards.get_reply_keyboard()
    )

# обработчик команды /info
@router.message(Command("info"))
async def info_command(message: Message) -> None:
    info_text = (
        "Valor bot — навигационный телеграм бот для новчиков на фондовом рынке.\n"
    )
    await message.answer(info_text, parse_mode="HTML")


# Список команд бота
@router.message(Command("help"))
async def help_command(message: Message) -> None:
    help_text = (
        "Доступные команды:\n"
    )
    await message.answer(help_text)


async def set_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Перезапустить бота"),
        BotCommand(command="help", description="Помощь и справка"),
        BotCommand(command="info", description="Информация о боте"),
        BotCommand(command="agreement", description="Пользовательское соглашение"),
        BotCommand(command="policy", description="Политика конфиденциальности")
    ]

    await bot.set_my_commands(commands, BotCommandScopeDefault())


@router.message(Command("cancel"))
async def cancel_command(message: Message, state: FSMContext) -> None:
    await _clear_state_preserving_valor_portfolio(state)
    await message.answer(
        "Текущее действие отменено.",
        reply_markup=await keyboards.get_reply_keyboard(),
    )


@router.message(
    StateFilter(*states.UserState.__all_states__), F.text.lower().in_(MENU_BUTTONS)
)
async def cancel_state_on_navigation(message: Message, state: FSMContext) -> None:
    await _clear_state_preserving_valor_portfolio(state)
    await message.answer(
        "Текущее действие отменено. Нажмите нужную кнопку еще раз.",
        reply_markup=await keyboards.get_reply_keyboard(),
    )


async def _clear_state_preserving_valor_portfolio(state: FSMContext) -> None:
    try:
        data = await state.get_data()
    except AttributeError:
        await state.clear()
        return
    temp_portfolio = data.get("valor_temp_portfolio")
    await state.clear()
    if temp_portfolio:
        await state.update_data(valor_temp_portfolio=temp_portfolio)


async def delete_sensitive_message(message: Message) -> None:
    try:
        await message.delete()
    except Exception as exc:
        logger.warning("Не удалось удалить сообщение с токеном: %s", exc)


# Обработчик команды /set_token. Запрашивает у пользователя токен T-Инвестиций и сохраняет его.
@router.message(Command("set_token"))
async def set_token_command(message: Message, state: FSMContext) -> None:
    await message.answer("Пожалуйста, отправьте ваш токен T-Инвестиций")
    await state.set_state(states.UserState.waiting_for_token)


# Обработчик получения токена от пользователя.
@router.message(states.UserState.waiting_for_token, F.text)
async def process_token(message: Message, state: FSMContext):
    user_id = message.from_user.id
    token = message.text.strip()
    logger.info(f"[User {user_id}] Попытка установки токена T-Инвестиций")

    try:
        async with AsyncClient(token=token) as client:
            await client.users.get_accounts()
            await requests.save_user_token(user_id, token)
            await delete_sensitive_message(message)
            await state.clear()
        return await message.answer("Токен успешно сохранен!")

    except AioRequestError as exc:
        await delete_sensitive_message(message)
        await state.clear()
        if exc.code.name in {"UNAUTHENTICATED", "PERMISSION_DENIED"}:
            logger.warning(f"[User {user_id}] Введен недействительный токен")
            await message.answer("Ваш токен недействителен")
        else:
            logger.error(
                "[User %s] Ошибка T-Invest при проверке токена: %s",
                user_id,
                exc,
                exc_info=True,
            )
            await message.answer(
                "T-Invest временно недоступен. Пожалуйста, попробуйте позже."
            )

    except Exception as e:
        logger.error(f"[User {user_id}] Системная ошибка при проверке/сохранении токена: {e}", exc_info=True)  # noqa: G201
        await delete_sensitive_message(message)
        await message.answer("Произошла ошибка при сохранении вашего токена. Пожалуйста, попробуйте позже.")
        await state.clear()


# Меню портфеля пользователя
@router.message(Command("portfolio"))
@router.message(F.text.lower() == "портфель")
async def portfolio_menu_command(message: Message) -> None:
    await message.answer(text="Портфель",
        reply_markup=await keyboards.get_portfolio_reply_keyboard())


# Возврат клавиатуры в главное меню
@router.message(Command("back_menu"))
@router.message(F.text.lower() == "назад в меню")
async def back_menu_command(message: Message) -> None:
    await message.answer(text="Главное меню",
        reply_markup=await keyboards.get_reply_keyboard())


# Вывод портфеля пользователя в форме таблицы
@router.message(F.text.lower() == "мой портфель")
async def send_table_tg(message: Message) -> None:
    user_id = message.from_user.id
    logger.info(f"[User {user_id}] Запросил просмотр портфеля")

    def cell(text: str, is_header: bool = False, align: str = "left", valign: str = "middle") -> RichBlockTableCell:
        return RichBlockTableCell(
            text=str(text),
            is_header=is_header,
            align=align,
            valign=valign
        )
    
    try:
        # Portfolio composition and quantities come exclusively from the
        # local user_portfolio table. get_user_portfolio joins the latest
        # cached instrument prices from instruments in the same DB query.
        portfolio = await requests.get_user_portfolio(user_id)
        
        if not portfolio:
            await message.answer("💼 Ваш портфель пока пуст. Добавьте первую бумагу!")
            return

        rows = [[
            cell("Бумага", is_header=True, align="center"),
            cell("Кол-во", is_header=True, align="center"),
            cell("Цена", is_header=True, align="center"),
            cell("Сумма", is_header=True, align="center"),
            cell("Изменение цены", is_header=True, align="center")
            ]]

        for paper in portfolio:
            instrument_type = paper.get("instrument_type")

            if instrument_type not in ("bond", "share"):
                continue

            quantity = int(paper.get("quantity") or 0)
            
            price_f = _portfolio_price(paper, instrument_type)
            open_f = _portfolio_open(paper, instrument_type)
            
            price_currency = _instrument_price_currency(paper, instrument_type)
            if instrument_type == "bond":
                paper_name = paper.get("bond_name") or "Без названия"
            else:
                paper_name = paper.get("name") or "Без названия"

            price_text = "Нет данных"
            summ_text = "Нет данных"
            delta_text = "Нет данных"

            if price_f is not None and price_f != 0:
                price_text = f"{price_f:.2f} {price_currency}"
                summ_text = f"{quantity * price_f:.2f} {price_currency}"

                if open_f is not None:
                    delta_price = (price_f - open_f) * quantity

                    sign = "+" if delta_price > 0 else ""
                    delta_text = f"{sign}{delta_price:.2f}"

            rows.append([
                cell(paper_name, align="right"), 
                cell(quantity, align="right"),  
                cell(price_text, align="right"),
                cell(summ_text, align="right"),
                cell(delta_text, align="right")
            ])

        table_block = InputRichBlockTable(cells=rows, is_bordered=True, is_striped=True)

        rich_msg = InputRichMessage(blocks=[table_block])

        await message.bot.send_rich_message(chat_id=message.chat.id, rich_message=rich_msg)
    except Exception as e:
        logger.error(f"[User {user_id}] Ошибка вывода портфеля: {e}", exc_info=True)  # noqa: G201
        await message.answer("Произошла ошибка при формировании портфеля. Попробуйте позже.")


# Кнопка добавления актива в портфель
@router.message(Command("add_active_command"))
@router.message(F.text.lower() == "добавить актив")
async def add_active_command(message: Message) -> None:
    await message.answer(text="Выберите способ добавления бумаги в портфель:",
        reply_markup=await keyboards.get_inline_keybord_portfolio_add_paper())


# Обработчик добавления бумаги в портфель
@router.callback_query(F.data == "add_paper_isin")
async def add_paper_isin(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.answer(
        "Пожалуйста, отправьте данные через пробел в формате:\n"
        "`ISIN Средняя цена Количество`\n\n"
        " *Пример:* `RU000A105GE2 985.5 10`",
        parse_mode="Markdown")
    await callback.answer()
    await state.set_state(states.UserState.add_paper_by_isin)


# Обработчик добавления бумаги по ISIN
@router.message(states.UserState.add_paper_by_isin, F.text)
async def process_add_isin(message: Message, state: FSMContext):

    raw_text = message.text.strip()
    user_id = message.from_user.id
    logger.info(f"[User {user_id}] Попытка добавления бумаги")

    user_data = raw_text.split()

    if len(user_data) != 3:
        logger.warning(f"[User {user_id}] Ошибка количества аргументов: ожидалось 3, получено {len(user_data)}")
        await message.answer(
            "❌ **Неверный формат ввода!**\n\n"
            "Пожалуйста, отправьте данные через пробел в формате:\n"
            "`ISIN Средняя цена Количество`\n\n"
            " *Пример:* `RU000A105GE2 985.5 10`",
            parse_mode="Markdown",
        )
        await state.clear()
        return

    raw_isin, raw_price, raw_quantity = user_data

    isin = raw_isin.strip().upper()
    if not isin.isalnum() or len(isin) < 4:
        logger.warning(f"[User {user_id}] Некорректный тикер/ISIN: '{isin}'")
        await message.answer(
            f"❌ **Некорректный ISIN или тикер:** `{isin}`\n"
            "Код бумаги должен состоять из букв и цифр (например, `RU000A105GE2`).",
            parse_mode="Markdown",
        )
        await state.clear()
        return
    
    try:
        avg_price = Decimal(raw_price.replace(",", "."))
        if not avg_price.is_finite() or avg_price < 0:
            raise InvalidOperation("Цена должна быть неотрицательным числом")
    except InvalidOperation as e:
        logger.warning(f"[User {user_id}] Ошибка парсинга цены '{raw_price}': {e}")
        await message.answer(
            f"❌ **Ошибка в цене:** `{raw_price}`\n"
            "Средняя цена должна быть положительным числом (например, `1000` или `985.5`).",
            parse_mode="Markdown",
        )
        await state.clear()
        return

    try:
        quantity = int(raw_quantity)
        if quantity <= 0:
            raise ValueError("Количество должно быть строго больше 0")
    except ValueError as e:
        logger.warning(f"[User {user_id}] Ошибка парсинга количества '{raw_quantity}': {e}")
        await message.answer(
            f"❌ **Ошибка в количестве:** `{raw_quantity}`\n"
            "Количество должно быть целым положительным числом (например, `10`).",
            parse_mode="Markdown",
        )
        await state.clear()
        return

    logger.info(f"[User {user_id}] Валидация пройдена: ISIN={isin}, Price={avg_price}, Qty={quantity}. Отправка в БД...")

    try:
        success = await requests.upload_user_portfolio(user_id=user_id, secid=isin, avg_price=avg_price, quantity=quantity)

    except Exception as e:
        logger.error(f"[User {user_id}] Критическая ошибка БД при сохранении {isin}: {e}", exc_info=True,)  # noqa: G201
        await message.answer("⚙️ Произошла ошибка на сервере при сохранении данных. Попробуйте позже.")
        await state.clear()
        return

    if success:
        logger.info(f"[User {user_id}] Бумага {isin} успешно сохранена.")
        await message.answer(
            f"✅ Бумага **{isin}** успешно добавлена/обновлена в Вашем портфеле!\n"
            f"📈 Средняя цена: `{avg_price}` | 📦 Количество: `{quantity}` шт.",
            parse_mode="Markdown",
        )
        await state.clear()
    else:
        logger.warning(f"[User {user_id}] Бумага {isin} не найдена в справочнике БД.")
        await message.answer(
            f"❌ Бумага с ISIN/тикером **{isin}** не найдена в наших справочниках. Проверьте правильность написания.",
            parse_mode="Markdown",
        )

    await state.clear()


# Кнопка удаления актива из портфеля
@router.message(Command("delete_active_command"))
@router.message(F.text.lower() == "удалить актив")
async def delete_active_command(message: Message) -> None:
    await message.answer(text="Напишите ISIN бумаги, которую хотите удалить из портфеля:",
        reply_markup=await keyboards.get_inline_keybord_portfolio_delete_paper())


# Обработчик удаления бумаги в портфель
@router.callback_query(F.data == "delete_paper_by_isin")
async def delete_paper_by_isin(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.answer("Отправьте ISIN бумаги")
    await callback.answer()
    await state.set_state(states.UserState.delete_paper_by_isin)


@router.message(states.UserState.delete_paper_by_isin, F.text)
async def process_delete_isin(message: Message, state: FSMContext):
    user_id = message.from_user.id
    isin = message.text.strip().upper()
    logger.info(f"[User {user_id}] Попытка удаления бумаги: '{isin}'")

    if not isin.isalnum() or len(isin) < 4:
        logger.warning(f"[User {user_id}] Некорректный тикер/ISIN при удалении: '{isin}'")
        await message.answer(
            f"❌ **Некорректный ISIN или тикер:** `{isin}`\n"
            "Код бумаги должен состоять из букв и цифр (например, `RU000A105GE2`).",
            parse_mode="Markdown",
        )
        return

    try:
        success = await requests.drop_isin_portfolio(user_id=user_id, secid=isin)
        if success:
            logger.info(f"[User {user_id}] Бумага {isin} успешно удалена")
            await message.answer(
                f"✅ Бумага **{isin}** успешно удалена из Вашего портфеля!\n",
                parse_mode="Markdown",
            )
        else:
            logger.warning(f"[User {user_id}] Бумага {isin} не найдена для удаления")
            await message.answer(
                f"❌ Бумага с ISIN/тикером **{isin}** не найдена в Вашем портфеле.",
                parse_mode="Markdown",
            )
    except Exception as e:
        logger.error(f"[User {user_id}] Ошибка удаления актива {isin}: {e}", exc_info=True)  # noqa: G201
        await message.answer("Произошла ошибка при удалении бумаги. Попробуйте позже.")
    finally:
        await state.clear()


# Обработчик удаления бумаги в портфель
@router.callback_query(F.data == "delete_portfolio")
async def delete_portfolio(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.answer(
        "Вы уверены, что хотите удалить портфель?\n" \
        "Отменить это действие будет невозможно.",
        reply_markup= await keyboards.get_agreement_keyboard()
        )
    await state.set_state(states.UserState.delete_portfolio)
    await callback.answer()


@router.callback_query(states.UserState.delete_portfolio, F.data.in_(["yes", "no"]))
async def process_delete_portfolio(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if callback.data == "yes":
        try:
            await requests.drop_user_portfolio(user_id)
            logger.info(f"[User {user_id}] Полностью удалил портфель")
            await callback.message.answer("Портфель успешно удален.")
        except Exception as e:
            logger.error(f"[User {user_id}] Ошибка при удалении портфеля: {e}", exc_info=True)  # noqa: G201
            await callback.message.answer("Произошла ошибка при удалении портфеля.")
    else:
        logger.info(f"[User {user_id}] Отменил удаление портфеля")
        await callback.message.answer("Отмена удаления портфеля.")
        
    await state.clear()
    await callback.answer()


# Меню облигаций
@router.message(Command("bonds"))
@router.message(F.text.lower() == "облигации")
async def bonds_command(message: Message) -> None:
    await message.answer("Доступные команды:", reply_markup=await keyboards.get_inline_keybord_bonds())


# Кнопка получения информации облигации по её ISIN
@router.callback_query(F.data == "get_bond_info")
async def get_bond_info(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.answer(
        "Введите название, тикер или ISIN облигации.\n"
        "Например: `ОФЗ`, `RU000A`, `SBER`.",
        parse_mode="Markdown",
    )
    await callback.answer()
    await state.set_state(states.UserState.search_instrument)
    await state.update_data(instrument_type="bond")


async def _show_instrument_results(
    message: Message, state: FSMContext, query: str, page: int = 0
) -> None:
    data = await state.get_data()
    instrument_type = data.get("instrument_type")
    if instrument_type not in {"bond", "share"}:
        await state.clear()
        await message.answer("Сессия поиска истекла. Откройте поиск бумаги заново.")
        return

    results, has_next = await requests.search_instruments(
        query=query,
        instrument_type=instrument_type,
        limit=8,
        offset=page * 8,
    )
    if not results and not catalog_is_ready():
        await message.answer(
            "Справочник бумаг еще обновляется. Попробуйте повторить поиск через несколько секунд."
        )
        return

    if not results and page == 0 and instrument_type == "share":
        user_id = data.get("search_user_id")
        try:
            broker_rows = await find_broker_neoassets_for_user(query, user_id)
            if broker_rows:
                await requests.upsert_instrument_catalog(broker_rows)
                results, has_next = await requests.search_instruments(
                    query=query,
                    instrument_type=instrument_type,
                    limit=8,
                )
        except Exception as exc:
            logger.error(
                "T-Invest fallback search failed for user %s: %s",
                user_id,
                exc,
                exc_info=True,
            )
    if not results:
        await message.answer(
            "Ничего не найдено. Попробуйте другую часть названия, тикер или ISIN."
        )
        return

    title = "облигаций" if instrument_type == "bond" else "акций и фондов"
    await message.answer(
        f"Результаты поиска {title} для <b>{html.quote(query)}</b>:",
        parse_mode="HTML",
        reply_markup=await keyboards.get_instrument_search_keyboard(
            results, page, has_next
        ),
    )


@router.message(states.UserState.search_instrument, F.text)
async def process_instrument_search(message: Message, state: FSMContext) -> None:
    query = message.text.strip()
    if len(query) < 2:
        await message.answer("Введите хотя бы 2 символа для поиска.")
        return
    await state.update_data(search_query=query)
    await state.update_data(search_user_id=message.from_user.id)
    await _show_instrument_results(message, state, query)


@router.callback_query(
    states.UserState.search_instrument,
    F.data.startswith("instrument_page:"),
)
async def instrument_search_page(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        page = int(callback.data.split(":", 1)[1])
    except (AttributeError, ValueError):
        await callback.answer("Некорректная страница поиска", show_alert=True)
        return

    data = await state.get_data()
    query = data.get("search_query")
    if not query:
        await callback.answer("Сессия поиска истекла", show_alert=True)
        await state.clear()
        return

    await callback.answer()
    await _show_instrument_results(callback.message, state, query, page)


@router.callback_query(
    states.UserState.search_instrument,
    F.data.startswith("instrument_select:"),
)
async def select_instrument(callback: CallbackQuery, state: FSMContext) -> None:
    secid = callback.data.partition(":")[2]
    await callback.answer()

    try:
        instrument = await requests.get_instrument_info(secid)
        if instrument is None:
            await callback.message.answer("Бумага больше не найдена в справочнике.")
            return

        reply_markup = await keyboards.get_add_to_portfolio_keyboard(secid)
        cached_text = _format_instrument_card(instrument)
        card_message = await callback.message.answer(
            cached_text,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )

        # The cached card is delivered immediately. Live T-Invest enrichment
        # happens afterwards and updates the same Telegram message.
        enriched = await refresh_and_store_instrument(
            instrument,
            user_id=callback.from_user.id,
        )
        live_text = _format_instrument_card(enriched)
        if live_text != cached_text:
            try:
                await card_message.edit_text(
                    live_text,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                )
            except Exception as exc:
                logger.warning(
                    "Не удалось обновить карточку %s live-ценой: %s",
                    secid,
                    exc,
                )

    except Exception as exc:
        logger.error("Ошибка вывода инструмента %s: %s", secid, exc, exc_info=True)
        await callback.message.answer("Не удалось получить данные бумаги.")


@router.callback_query(
    states.UserState.search_instrument, F.data == "instrument_cancel"
)
async def cancel_instrument_search(
    callback: CallbackQuery, state: FSMContext
) -> None:
    await state.clear()
    await callback.answer("Поиск отменен")
    await callback.message.edit_reply_markup(reply_markup=None)


@router.callback_query(F.data.startswith("portfolio_add:"))
async def start_add_selected_instrument(
    callback: CallbackQuery, state: FSMContext
) -> None:
    secid = callback.data.partition(":")[2]
    instrument = await requests.get_instrument_info(secid)
    if instrument is None:
        await callback.answer("Бумага больше не найдена", show_alert=True)
        return

    await state.set_state(states.UserState.add_selected_instrument)
    await state.update_data(secid=secid)
    await callback.answer()
    await callback.message.answer(
        "Отправьте среднюю цену покупки и количество через пробел:\n"
        "<code>985.50 10</code>\n\n"
        "Первое значение — средняя цена, второе — количество бумаг.",
        parse_mode="HTML",
    )


def _parse_position_input(raw_text: str) -> tuple[Decimal, int]:
    values = raw_text.replace(",", ".").split()
    if len(values) != 2:
        raise ValueError("Ожидаются средняя цена и количество")

    try:
        avg_price = Decimal(values[0])
    except InvalidOperation as exc:
        raise ValueError("Цена должна быть числом") from exc
    if not avg_price.is_finite() or avg_price <= 0:
        raise ValueError("Цена должна быть положительным числом")

    try:
        quantity = int(values[1])
    except ValueError as exc:
        raise ValueError("Количество должно быть целым числом") from exc
    if quantity <= 0:
        raise ValueError("Количество должно быть больше нуля")

    return avg_price, quantity


@router.message(states.UserState.add_selected_instrument, F.text)
async def process_add_selected_instrument(
    message: Message, state: FSMContext
) -> None:
    try:
        avg_price, quantity = _parse_position_input(message.text)
    except ValueError as exc:
        await message.answer(
            f"Некорректный формат: {exc}.\n"
            "Пример: <code>985.50 10</code>",
            parse_mode="HTML",
        )
        return

    data = await state.get_data()
    secid = data.get("secid")
    if not secid:
        await state.clear()
        await message.answer("Сессия добавления истекла. Выберите бумагу заново.")
        return

    try:
        saved = await requests.upload_user_portfolio(
            user_id=message.from_user.id,
            secid=secid,
            avg_price=avg_price,
            quantity=quantity,
        )
        await state.clear()
        if not saved:
            await message.answer("Бумага не найдена в справочнике.")
            return
        await message.answer(
            f"✅ Бумага <b>{html.quote(secid)}</b> добавлена в портфель.\n"
            f"Средняя цена: <b>{avg_price}</b>\n"
            f"Количество: <b>{quantity}</b>",
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.error(
            "Ошибка добавления %s в портфель пользователя %s: %s",
            secid,
            message.from_user.id,
            exc,
            exc_info=True,
        )
        await state.clear()
        await message.answer("Не удалось добавить бумагу в портфель.")


def _format_instrument_card(instrument: dict) -> str:
    def safe_float(value) -> float | None:
        try:
            return float(value) if value is not None else None
        except (ValueError, TypeError):
            return None

    instrument_type = instrument.get("instrument_type")
    name = instrument.get("bond_name") or instrument.get("name") or "Без названия"
    name = html.quote(str(name))
    secid = html.quote(str(instrument.get("secid") or "Н/Д"))
    isin = html.quote(str(instrument.get("isin") or "Н/Д"))
    currency = html.quote(
        _instrument_price_currency(instrument, instrument_type, default="Н/Д")
    )
    raw_price = instrument.get(
        "last_price" if instrument_type == "bond" else "last"
    )
    if raw_price is None:
        raw_price = instrument.get("last_price")
    price = safe_float(raw_price)
    price_text = f"{price:.2f} {currency}" if price is not None else "Нет данных"
    price_source = instrument.get("price_source")
    price_date = html.quote(str(instrument.get("price_date") or ""))
    if price_source == "t_invest":
        price_note = "T-Invest, цена последней сделки"
    elif price_source == "previous_close":
        price_note = "Цена предыдущего торгового дня"
        if price_date:
            price_note += f" ({price_date})"
    elif price_source == "previous_reference":
        price_note = "Последняя reference-цена предыдущей сессии"
        if price_date:
            price_note += f" ({price_date})"
    elif price_source == "trade":
        price_note = "MOEX, данные могут быть с задержкой до 15 минут"
    elif price_source == "market_reference":
        price_note = "Последняя доступная цена MOEX, данные могут быть с задержкой"
    elif price_source == "quote":
        price_note = "Оценка по заявкам Bid/Offer, данные могут быть с задержкой"
    else:
        price_note = "Последняя доступная цена MOEX"

    if instrument_type == "bond":
        type_name = "Облигация"
    elif instrument.get("asset_type") == "etf":
        type_name = "Фонд (ETF)"
    elif instrument.get("asset_type") == "neoasset":
        type_name = "Неоактив"
    else:
        type_name = "Акция"

    text = (
        f"📈 <b>{name}</b>\n"
        f"• <b>Тикер:</b> <code>{secid}</code>\n"
        f"• <b>ISIN:</b> <code>{isin}</code>\n"
        f"• <b>Тип:</b> {html.quote(type_name)}\n"
        f"• <b>Валюта:</b> {currency}\n"
        f"• <b>Цена:</b> {price_text}\n"
        f"• <b>Источник:</b> {price_note}\n"
    )

    if instrument_type == "bond":
        face_value = safe_float(instrument.get("face_value"))
        coupon_percent = safe_float(instrument.get("coupon_percent"))
        maturity = formatting.format_date(instrument.get("matdate"))
        coupon_value = safe_float(instrument.get("coupon_value"))
        effectiveyield = safe_float(instrument.get("effectiveyield"))
        if face_value is not None:
            text += f"• <b>Номинал:</b> {face_value:.2f} {currency}\n"
        coupon_parts = []
        if coupon_value is not None:
            coupon_parts.append(f"{coupon_value:.2f} {currency}")
        if coupon_percent is not None:
            coupon_parts.append(f"{coupon_percent:.2f}%")
        text += f"• <b>Купон:</b> {' / '.join(coupon_parts) or 'Н/Д'}\n"
        text += (
            f"• <b>Дата погашения:</b> {maturity}\n"
            f"• <b>YLT:</b> {effectiveyield:.2f}%\n"
            if effectiveyield is not None
            else "• <b>YLT:</b> Н/Д\n"
        )
        text += (
            f"• <b>Подробнее:</b> https://analytics.dohod.ru/bond/{isin}\n")

    return text


# Обработчик вывода данных по облигациям
@router.message(states.UserState.get_bond_by_isin, F.text)
async def process_bond_info(message: Message, state: FSMContext):
    user_id = message.from_user.id
    isin = message.text.strip().upper()
    await state.clear()
    logger.info(f"[User {user_id}] Ищет информацию по облигации {isin}")
    
    def safe_float(value, default=0.0):
        try:
            return float(value) if value is not None else default
        except (ValueError, TypeError):
            return default

    try:
        bond_info = await requests.get_bonds_info(isin)

        if not bond_info:
            logger.info(f"[User {user_id}] Облигация {isin} не найдена")
            await message.answer("Облигация с таким ISIN не найдена.")
            return
        bond_info = await refresh_and_store_instrument(
            bond_info,
            user_id=user_id,
        )

        bond_isin = bond_info.get("isin")
        bond_name = bond_info.get("bond_name", "Без названия")
        currency = _instrument_price_currency(bond_info, "bond", default="Н/Д")

        raw_price = bond_info.get("last_price")
        price = _safe_float(raw_price)
        price_text = f"{price:.2f} {currency}" if price is not None else "Нет данных"

        accruedint = safe_float(bond_info.get("accruedint"))
        face_value = safe_float(bond_info.get("face_value"))
        coupon_value = safe_float(bond_info.get("coupon_value"))
        coupon_percent = safe_float(bond_info.get("coupon_percent"))
        coupon_period = safe_float(bond_info.get("coupon_period"))
        coupon_payments = round(365 / coupon_period, 1) if coupon_period > 0 else 0

        matdate_text = formatting.format_date(bond_info.get("matdate")) if bond_info.get("matdate") else "Н/Д"
        next_coupon_text = formatting.format_date(bond_info.get("next_coupon")) if bond_info.get("next_coupon") else "Н/Д"

        text = (
            f"📈 <b>{bond_name}</b> (<code>{bond_isin}</code>)\n\n"
            f"• <b>Номинал:</b> {face_value:.2f} {currency}.\n"
            f"• <b>Купон:</b> {coupon_value:.2f} {currency}. ({coupon_percent:.2f}%)\n"
            f"• <b>Купонные выплаты в год:</b> {coupon_payments:g}\n"
            f"• <b>НКД:</b> {accruedint:.2f} {currency}.\n"
            f"• <b>Текущая цена:</b> {price_text}\n"
            f"• <b>Следующий купон:</b> {next_coupon_text}\n"
            f"• <b>Дата погашения:</b> {matdate_text}\n"
            f"• <b>Подробнее:</b> https://analytics.dohod.ru/bond/{bond_isin}"
        )
        await message.answer(text, parse_mode="HTML")

    except Exception as e:
        logging.error(f"Ошибка при получении данных об облигации {isin}: {e}", exc_info=True)  # noqa: G201, LOG015
        await message.answer("Произошла системная ошибка при обработке запроса.")


# Меню Акций и фондов
@router.message(Command("shares_etfs"))
@router.message(F.text.lower() == "акции и фонды")
async def shares_etfs_command(message: Message) -> None:
    await message.answer("Доступные команды:", reply_markup=await keyboards.get_inline_keybord_shares_etfs())


# Кнопка получения информации облигации по её ISIN
@router.callback_query(F.data == "get_share_etf_info")
async def get_shares_etf_info(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.answer(
        "Введите название, тикер или ISIN акции, фонда или неоактива.\n"
        "Например: `Сбер`, `SBER`, `RU0009029540`.",
        parse_mode="Markdown",
    )
    await callback.answer()
    await state.set_state(states.UserState.search_instrument)
    await state.update_data(instrument_type="share")


@router.message(states.UserState.get_share_etf_by_isin, F.text)
async def process_share_etf_info(message: Message, state: FSMContext):

    user_id = message.from_user.id
    isin_secid = message.text.strip().upper()
    await state.clear()
    logger.info(f"[User {user_id}] Ищет информацию по акции/фонду {isin_secid}")

    try:
        share_etf_info = await requests.get_share_etf_info(isin_secid)

        if not share_etf_info:
            logger.info(f"[User {user_id}] Акция/фонд {isin_secid} не найдена")
            await message.answer("Акция или фонд с таким ISIN/тикером не найдено.")
            return
        share_etf_info = await refresh_and_store_instrument(
            share_etf_info,
            user_id=user_id,
        )

        paper_name = share_etf_info.get("name", "Без названия")

        last_price = _safe_float(share_etf_info.get("last"))
        if last_price is None:
            last_price = _safe_float(share_etf_info.get("last_price"))
        currency = _instrument_price_currency(
            share_etf_info, "share", default="Н/Д"
        )
        price_text = (
            f"{last_price:.2f} {currency}"
            if last_price is not None
            else "Нет данных"
        )

        text = (
            f"📈 <b>{paper_name}</b> (<code>{isin_secid}</code>)\n\n"
            f"• <b>Текущая цена:</b> {price_text}.\n"
        )
        await message.answer(text, parse_mode="HTML")

    except Exception as e:
        logging.error(f"Ошибка при получении данных об акции/фонде {isin_secid}: {e}", exc_info=True)  # noqa: G201, LOG015
        await message.answer("Произошла системная ошибка при обработке запроса.")


def _valor_temp_portfolio(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    stored = data.get("valor_temp_portfolio")
    return dict(stored) if isinstance(stored, dict) else {}


def _format_valor_temp_portfolio(
    items: list[dict[str, Any]], *, page: int = 0, page_size: int = 8
) -> str:
    if not items:
        return (
            "🧺 <b>Временный портфель Valor</b>\n\n"
            "Он пока пуст. Откройте карточку бумаги и нажмите "
            "«Во временный портфель»."
        )

    max_page = max(0, (len(items) - 1) // page_size)
    page = max(0, min(page, max_page))
    start = page * page_size
    visible_items = items[start : start + page_size]
    lines = [
        "🧺 <b>Временный портфель Valor</b>",
        f"Позиции {start + 1}–{start + len(visible_items)} из {len(items)}.",
        "",
    ]
    totals: dict[str, Decimal] = {}
    for item in items:
        price = Decimal(str(item["avg_price"]))
        quantity = int(item["quantity"])
        currency = _display_currency(item.get("currency"))
        position_total = price * quantity
        totals[currency] = totals.get(currency, Decimal("0")) + position_total
    for item in visible_items:
        price = Decimal(str(item["avg_price"]))
        quantity = int(item["quantity"])
        currency = _display_currency(item.get("currency"))
        position_total = price * quantity
        lines.append(
            f'• <b>{html.quote(str(item["identifier"]))}</b> — '
            f'{quantity} × {price:g} {html.quote(currency)} = '
            f'{position_total:g} {html.quote(currency)}'
        )

    lines.extend(["", "<b>Итого:</b>"])
    for currency, total in sorted(totals.items()):
        lines.append(f"• {total:g} {html.quote(currency)}")
    lines.extend(["", "Цены и количества можно изменить, добавив бумагу повторно."])
    return "\n".join(lines)


async def _show_valor_menu(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    temp_count = len(_valor_temp_portfolio(data))
    await message.answer(
        "📚 <b>Подборка Valor</b>\n\n"
        "Здесь собраны акции и облигации из экспертной таблицы Valor. "
        "Выберите раздел или найдите бумагу по названию, тикеру либо ISIN.",
        parse_mode="HTML",
        reply_markup=await keyboards.get_valor_menu_keyboard(temp_count),
    )


async def _show_valor_assets(
    message: Message,
    *,
    asset_type: str | None = None,
    query: str | None = None,
    page: int = 0,
) -> None:
    results, has_next = await requests.list_valor_assets(
        asset_type=asset_type,
        query=query,
        limit=8,
        offset=page * 8,
    )
    if not results:
        await message.answer(
            "В подборке Valor ничего не найдено. Попробуйте другой запрос."
        )
        return

    if query:
        title = f'Результаты поиска для <b>{html.quote(query)}</b>:'
    else:
        title = "Акции Valor:" if asset_type == "share" else "Облигации Valor:"
    await message.answer(
        title,
        parse_mode="HTML",
        reply_markup=await keyboards.get_valor_assets_keyboard(
            results,
            page=page,
            has_next=has_next,
            asset_type=asset_type,
            is_search=bool(query),
        ),
    )


@router.message(F.text.lower() == "подборка valor")
async def valor_command(message: Message, state: FSMContext) -> None:
    await state.set_state(None)
    await _show_valor_menu(message, state)


@router.callback_query(F.data == "valor_menu")
async def valor_menu_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(None)
    await callback.answer()
    await _show_valor_menu(callback.message, state)


@router.callback_query(F.data.startswith("valor_list:"))
async def valor_list_callback(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) != 3 or parts[1] not in {"share", "bond"}:
        await callback.answer("Некорректный раздел", show_alert=True)
        return
    try:
        page = max(0, int(parts[2]))
    except ValueError:
        await callback.answer("Некорректная страница", show_alert=True)
        return
    await callback.answer()
    await _show_valor_assets(callback.message, asset_type=parts[1], page=page)


@router.callback_query(F.data == "valor_search")
async def start_valor_search(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(states.UserState.valor_search)
    await callback.answer()
    await callback.message.answer(
        "Введите название, тикер или ISIN бумаги из подборки Valor.\n"
        "Например: <code>Сбер</code>, <code>SBER</code> или <code>RU000A10</code>.",
        parse_mode="HTML",
    )


@router.message(states.UserState.valor_search, F.text)
async def process_valor_search(message: Message, state: FSMContext) -> None:
    query = message.text.strip()
    if len(query) < 2:
        await message.answer("Введите хотя бы 2 символа для поиска.")
        return
    await state.update_data(valor_search_query=query)
    await _show_valor_assets(message, query=query)


@router.callback_query(
    states.UserState.valor_search,
    F.data.startswith("valor_search_page:"),
)
async def valor_search_page(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        page = max(0, int((callback.data or "").partition(":")[2]))
    except ValueError:
        await callback.answer("Некорректная страница", show_alert=True)
        return
    query = (await state.get_data()).get("valor_search_query")
    if not query:
        await callback.answer("Сессия поиска истекла", show_alert=True)
        return
    await callback.answer()
    await _show_valor_assets(callback.message, query=query, page=page)


@router.callback_query(F.data.startswith("valor_asset:"))
async def show_valor_asset(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        asset_id = int((callback.data or "").partition(":")[2])
    except ValueError:
        await callback.answer("Некорректная бумага", show_alert=True)
        return
    asset = await requests.get_valor_asset(asset_id)
    if asset is None:
        await callback.answer("Бумага больше не найдена", show_alert=True)
        return
    await state.set_state(None)
    await callback.answer()
    await callback.message.answer(
        format_valor_asset_profile(asset),
        parse_mode="HTML",
        reply_markup=await keyboards.get_valor_asset_keyboard(asset_id),
    )


@router.callback_query(F.data.startswith("valor_temp_add:"))
async def start_valor_temp_add(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        asset_id = int((callback.data or "").partition(":")[2])
    except ValueError:
        await callback.answer("Некорректная бумага", show_alert=True)
        return
    asset = await requests.get_valor_asset(asset_id)
    if asset is None:
        await callback.answer("Бумага больше не найдена", show_alert=True)
        return
    await state.set_state(states.UserState.valor_add_position)
    await state.update_data(valor_pending_asset_id=asset_id)
    await callback.answer()
    await callback.message.answer(
        f'Введите среднюю цену и количество для <b>{html.quote(asset["identifier"])}</b> '
        "через пробел:\n<code>250.50 10</code>",
        parse_mode="HTML",
    )


@router.message(states.UserState.valor_add_position, F.text)
async def process_valor_temp_add(message: Message, state: FSMContext) -> None:
    try:
        avg_price, quantity = _parse_position_input(message.text)
    except ValueError as exc:
        await message.answer(
            f"Некорректный формат: {html.quote(str(exc))}.\n"
            "Пример: <code>250.50 10</code>",
            parse_mode="HTML",
        )
        return

    data = await state.get_data()
    asset_id = data.get("valor_pending_asset_id")
    asset = await requests.get_valor_asset(asset_id) if asset_id else None
    if asset is None:
        await state.set_state(None)
        await message.answer("Сессия добавления истекла. Выберите бумагу заново.")
        return

    temp_portfolio = _valor_temp_portfolio(data)
    temp_portfolio[str(asset_id)] = {
        "asset_id": asset_id,
        "asset_type": asset["asset_type"],
        "identifier": asset["identifier"],
        "issuer": asset["issuer"],
        "currency": asset.get("currency") or "RUB",
        "avg_price": str(avg_price),
        "quantity": quantity,
    }
    await state.update_data(valor_temp_portfolio=temp_portfolio)
    await state.set_state(None)
    await message.answer(
        f'✅ <b>{html.quote(asset["identifier"])}</b> добавлена во временный портфель.',
        parse_mode="HTML",
        reply_markup=await keyboards.get_valor_menu_keyboard(len(temp_portfolio)),
    )


@router.callback_query(F.data.startswith("valor_temp_view"))
async def show_valor_temp_portfolio(
    callback: CallbackQuery, state: FSMContext
) -> None:
    raw_page = (callback.data or "").partition(":")[2]
    try:
        page = max(0, int(raw_page)) if raw_page else 0
    except ValueError:
        await callback.answer("Некорректная страница", show_alert=True)
        return
    items = list(_valor_temp_portfolio(await state.get_data()).values())
    items.sort(key=lambda item: (item["asset_type"], item["identifier"]))
    max_page = max(0, (len(items) - 1) // 8)
    page = min(page, max_page)
    await callback.answer()
    await callback.message.answer(
        _format_valor_temp_portfolio(items, page=page),
        parse_mode="HTML",
        reply_markup=await keyboards.get_valor_temp_portfolio_keyboard(
            items, page=page
        ),
    )


@router.callback_query(F.data.startswith("valor_temp_remove:"))
async def remove_from_valor_temp_portfolio(
    callback: CallbackQuery, state: FSMContext
) -> None:
    parts = (callback.data or "").split(":")
    asset_id = parts[1] if len(parts) > 1 else ""
    try:
        page = max(0, int(parts[2])) if len(parts) > 2 else 0
    except ValueError:
        page = 0
    temp_portfolio = _valor_temp_portfolio(await state.get_data())
    removed = temp_portfolio.pop(asset_id, None)
    await state.update_data(valor_temp_portfolio=temp_portfolio)
    await callback.answer("Бумага удалена" if removed else "Бумага уже удалена")
    items = list(temp_portfolio.values())
    items.sort(key=lambda item: (item["asset_type"], item["identifier"]))
    page = min(page, max(0, (len(items) - 1) // 8))
    await callback.message.answer(
        _format_valor_temp_portfolio(items, page=page),
        parse_mode="HTML",
        reply_markup=await keyboards.get_valor_temp_portfolio_keyboard(
            items, page=page
        ),
    )


@router.callback_query(F.data == "valor_temp_clear")
async def clear_valor_temp_portfolio(
    callback: CallbackQuery, state: FSMContext
) -> None:
    await state.update_data(valor_temp_portfolio={})
    await callback.answer("Временный портфель очищен")
    await callback.message.answer(
        _format_valor_temp_portfolio([]),
        parse_mode="HTML",
        reply_markup=await keyboards.get_valor_temp_portfolio_keyboard([]),
    )


@router.callback_query(F.data == "valor_temp_transfer")
async def transfer_valor_temp_portfolio(
    callback: CallbackQuery, state: FSMContext
) -> None:
    temp_portfolio = _valor_temp_portfolio(await state.get_data())
    if not temp_portfolio:
        await callback.answer("Временный портфель пуст", show_alert=True)
        return

    transferred = []
    failed = []
    for item in temp_portfolio.values():
        try:
            saved = await requests.upload_user_portfolio(
                user_id=callback.from_user.id,
                secid=item["identifier"],
                avg_price=Decimal(item["avg_price"]),
                quantity=int(item["quantity"]),
            )
        except Exception as exc:
            logger.error(
                "Не удалось перенести Valor-бумагу %s пользователю %s: %s",
                item["identifier"],
                callback.from_user.id,
                exc,
                exc_info=True,
            )
            saved = False
        if saved:
            transferred.append(item["identifier"])
        else:
            failed.append(item["identifier"])

    transferred_set = set(transferred)
    temp_portfolio = {
        key: item
        for key, item in temp_portfolio.items()
        if item["identifier"] not in transferred_set
    }
    await state.update_data(valor_temp_portfolio=temp_portfolio)
    await callback.answer()

    lines = [f"✅ В основной портфель добавлено: <b>{len(transferred)}</b>."]
    if failed:
        lines.append(
            "Не удалось сопоставить со справочником: "
            + ", ".join(html.quote(item) for item in failed)
            + ". Они оставлены во временном портфеле."
        )
    await callback.message.answer(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=await keyboards.get_valor_menu_keyboard(len(temp_portfolio)),
    )


@router.message(F.text.lower() == "анализ моего портфеля")
async def portfolio_analysis_command(message: Message) -> None:
    user_id = message.from_user.id
    logger.info(f"[User {user_id}] Запросил анализ своего портфеля")

    try:
        portfolio = await requests.get_user_portfolio(user_id)
        if not portfolio:
            await message.answer(
                "📊 <b>Анализ портфеля Valor</b>\n\n"
                "Ваш портфель пока пуст. Добавьте активы в разделе "
                "<b>Портфель</b>, и я рассчитаю шесть риск-факторов по модели Valor.",
                parse_mode="HTML",
            )
            return

        positions = []
        rating_keys: set[tuple[str, str]] = set()

        for paper in portfolio:
            asset_type = str(paper.get("instrument_type") or "").lower()
            if asset_type == "bond":
                identifier = str(paper.get("isin") or "").strip().upper()
                currency = _instrument_price_currency(paper, asset_type)
            elif asset_type == "share":
                identifier = str(
                    paper.get("secid") or paper.get("ticker") or ""
                ).strip().upper()
                currency = _instrument_price_currency(paper, asset_type)
            else:
                continue

            quantity = _safe_float(paper.get("quantity"))
            price = _portfolio_price(paper, asset_type)
            uses_average_price = False
            if price is None:
                price = _safe_float(paper.get("avg_price"))
                uses_average_price = price is not None
            market_value = (
                quantity * price
                if quantity is not None and quantity > 0 and price is not None
                else None
            )

            positions.append(
                {
                    "asset_type": asset_type,
                    "identifier": identifier,
                    "currency": currency,
                    "market_value": market_value,
                    "uses_average_price": uses_average_price,
                }
            )
            if identifier:
                rating_keys.add((asset_type, identifier))

        profiles = await requests.get_valor_risk_profiles(rating_keys)
        report = calculate_portfolio_risks(positions, profiles)
        await message.answer(format_portfolio_risks(report), parse_mode="HTML")
    except Exception as exc:
        logger.error(
            "[User %s] Ошибка анализа портфеля: %s",
            user_id,
            exc,
            exc_info=True,
        )
        await message.answer("Не удалось проанализировать портфель. Попробуйте позже.")


# Обработчик команды /delete_token. Удаляет сохраненный токен T-Инвестиций пользователя.
@router.message(Command("delete_token"))
async def delete_token_command(message: Message) -> None:
    user_id = message.from_user.id
    try:
        deleted = await requests.delete_user_token(user_id)
        if deleted:
            logger.info(f"[User {user_id}] Успешно удалил токен")
            await message.answer("Токен успешно удален!")
        else:
            await message.answer("Сохраненный токен не найден.")
    except Exception as e:
        logger.error(f"[User {user_id}] Ошибка при удалении токена: {e}", exc_info=True)  # noqa: G201
        await message.answer("Не удалось удалить токен. Попробуйте позже.")


async def sync_portfolio_by_token(message: Message, user_id: int) -> None:
    logger.info(f"[User {user_id}] Запрос на загрузку портфеля по токену")
    
    try:
        user_token = await resolve_private_user_token(user_id)
        if not user_token:
            await message.answer(
                "Для загрузки личного портфеля необходимо привязать свой токен "
                "с помощью команды /set_token. Системный токен используется только "
                "для общедоступных рыночных данных."
            )
            return

        portfolio = await portfolio_service.get_user_portfolio_token(user_token)
        saved_count, skipped = await requests.sync_user_portfolio(user_id, portfolio)
        if not portfolio:
            await message.answer(
                "T-Invest не вернул позиции. Локальный портфель не изменен; "
                "для очистки используйте отдельную команду удаления портфеля."
            )
            return

        if saved_count == 0:
            await message.answer(
                "Не удалось сопоставить позиции со справочником инструментов. "
                "Сначала обновите справочник MOEX."
            )
            return

        logger.info(f"[User {user_id}] Портфель успешно загружен по токену")
        result = f"Портфель синхронизирован. Загружено позиций: {saved_count}."
        if skipped:
            result += (
                f" Не удалось сопоставить: {len(skipped)}. "
                "Существующие локальные позиции сохранены."
            )
        await message.answer(result)
    except AioRequestError as exc:
        if exc.code.name == "UNAUTHENTICATED":
            discarded = await discard_rejected_private_user_token(
                user_id,
                user_token,
            )
            logger.warning(
                "[User %s] Сохраненный token T-Invest отклонен при "
                "синхронизации портфеля",
                user_id,
            )
            if discarded:
                await message.answer(
                    "Сохраненный токен T-Invest больше не действует и был "
                    "удален. Привяжите новый токен с помощью команды /set_token."
                )
            else:
                await message.answer(
                    "Использованный токен T-Invest был отклонен. Проверьте "
                    "актуальный токен с помощью команды /set_token."
                )
            return

        logger.error(
            "[User %s] Ошибка T-Invest при синхронизации портфеля: %s",
            user_id,
            exc,
            exc_info=True,
        )
        await message.answer("Произошла ошибка при загрузке портфеля.")
    except Exception as e:
        logger.error(f"[User {user_id}] Ошибка при синхронизации портфеля по токену: {e}", exc_info=True)
        await message.answer("Произошла ошибка при загрузке портфеля.")


# Загрузка портфеля по токену
@router.message(Command("set_portfolio_by_token"))
async def set_portfolio_command(message: Message) -> None:
    await sync_portfolio_by_token(message, message.from_user.id)


@router.callback_query(F.data == "get_portfolio_token")
async def set_portfolio_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    await sync_portfolio_by_token(callback.message, callback.from_user.id)


@router.message(Command("agreement"))
async def agreement_command(message: Message) -> None:
    await message.answer("https://telegra.ph/Polzovatelskoe-soglashenie-07-29-23")

@router.message(Command("policy"))
async def policy_command(message: Message) -> None:
    await message.answer("https://telegra.ph/Politika-konfidencialnosti-07-29-65")
