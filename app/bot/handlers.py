import logging

import app.bot.keyboard as keyboards
import app.services.portfolio_servise as portfolio_service
from aiogram import Bot, F, Router, html
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
from t_tech.invest import AsyncClient, RequestError

router = Router()
logger = logging.getLogger("handlers")


# обработчик команды /start
@router.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    await message.answer(
        f"Привет, {html.bold(message.from_user.full_name)}!\n"
        "Это бот команды <b>Valor</b>. Наша цель — помочь новичкам " \
        " освоиться на фондовом рынке.\n\n"
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


# Обработчик команды /set_token. Запрашивает у пользователя токен T-Инвестиций и сохраняет его.
@router.message(Command("set_token"))
async def set_token_command(message: Message, state: FSMContext) -> None:
    await message.answer("Пожалуйста, отправьте ваш токен T-Инвестиций")
    await state.set_state(states.UserState.waiting_for_token)


# Обработчик получения токена от пользователя.
@router.message(states.UserState.waiting_for_token)
async def process_token(message: Message, state: FSMContext):
    user_id = message.from_user.id
    token = message.text.strip()
    logger.info(f"[User {user_id}] Попытка установки токена T-Инвестиций")

    try:
        async with AsyncClient(token=token) as client:
            await client.users.get_accounts()
            await requests.save_user_token(user_id, token)
            await message.delete()
            await state.clear()
        return await message.answer("Токен успешно сохранен!")

    except RequestError:
        logger.warning(f"[User {user_id}] Введен недействительный токен")
        await message.delete()
        await message.answer("Ваш токен нейдействителен")
        await state.clear()

    except Exception as e:
        logger.error(f"[User {user_id}] Системная ошибка при проверке/сохранении токена: {e}", exc_info=True)  # noqa: G201
        await message.delete()
        await message.answer("Произошла ошибка при сохранении вашего токена. Пожалуйста, попробуйте позже.")
        await state.clear()


# Меню портфеля пользователя
@router.message(Command("Portfolio"))
@router.message(F.text.lower() == "портфель")
async def portfolio_menu_command(message: Message) -> None:
    await message.answer(text="Портфель",
        reply_markup=await keyboards.get_portfolio_reply_keyboard())


# Возврат клавиатуры в главное меню
@router.message(Command("Back_menu"))
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
            
            raw_price = paper.get("last")
            raw_open = paper.get("open")
            
            faceunit = "RUB"
            if instrument_type == "bond":
                paper_name = paper.get("bond_name") or "Без названия"
                raw_faceunit = paper.get("faceunit")
                if raw_faceunit and raw_faceunit != "SUR":
                    faceunit = raw_faceunit
            else:
                paper_name = paper.get("name") or "Без названия"

            price_text = "Нет данных"
            summ_text = "Нет данных"
            delta_text = "Нет данных"

            if raw_price is not None:
                try:
                    price_f = float(raw_price)
                    if price_f != 0:
                        price_text = f"{price_f:.2f} {faceunit}"
                        summ_text = f"{quantity * price_f:.2f} {faceunit}"

                        if raw_open is not None:
                            open_f = float(raw_open)
                            delta_price = (price_f - open_f) * quantity

                            sign = "+" if delta_price > 0 else ""
                            delta_text = f"{sign}{delta_price:.2f}"
                            
                except (ValueError, TypeError):
                    pass

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
@router.message(states.UserState.add_paper_by_isin)
async def process_add_isin(message: Message, state: FSMContext):

    raw_text = message.text.strip()
    user_id = message.from_user.id
    logger.info(f"[User {user_id}] Попытка добавления бумаги. Введенный текст: '{raw_text}'")

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
        avg_price = float(raw_price.replace(",", "."))
        if avg_price < 0:
            raise ValueError("Цена не может быть отрицательной")
    except ValueError as e:
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


@router.message(states.UserState.delete_paper_by_isin)
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
        success = await requests.drop_isin_portfolio(user_id=user_id, isin=isin)
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
    await message.answer("Доступне команды:", reply_markup=await keyboards.get_inline_keybord_bonds())


# Кнопка получения информации облигации по её ISIN
@router.callback_query(F.data == "get_bond_info")
async def get_bond_info(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.answer("Отправьте ISIN облигации")
    await callback.answer()
    await state.set_state(states.UserState.get_bond_by_isin)


# Обработчик вывода данных по облигациям
@router.message(states.UserState.get_bond_by_isin)
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

        bond_isin = bond_info.get("isin")
        bond_name = bond_info.get("bond_name", "Без названия")
        faceunit = "RUB" if bond_info.get("faceunit") in ("SUR", None) else bond_info.get("faceunit")

        raw_price = bond_info.get("last")
        price_text = f"{float(raw_price):.2f} руб." if raw_price is not None else "Нет данных"

        accruedint = safe_float(bond_info.get("accruedint"))
        face_value = safe_float(bond_info.get("face_value"))
        coupon_value = safe_float(bond_info.get("coupon_value"))
        coupon_percent = safe_float(bond_info.get("coupon_percent"))
        coupon_period = bond_info.get("coupon_period") or 0

        matdate_text = formatting.format_date(bond_info.get("matdate")) if bond_info.get("matdate") else "Н/Д"
        next_coupon_text = formatting.format_date(bond_info.get("next_coupon")) if bond_info.get("next_coupon") else "Н/Д"

        text = (
            f"📈 <b>{bond_name}</b> (<code>{bond_isin}</code>)\n\n"
            f"• <b>Номинал:</b> {face_value:.2f} {faceunit}.\n"
            f"• <b>Купон:</b> {coupon_value:.2f} {faceunit}. ({coupon_percent:.2f}%)\n"
            f"• <b>Купонные выплаты в год:</b> {coupon_period}\n"
            f"• <b>НКД:</b> {accruedint:.2f} руб.\n"
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
    await callback.message.answer("Отправьте тикер или ISIN акции или фонда")
    await callback.answer()
    await state.set_state(states.UserState.get_share_etf_by_isin)


@router.message(states.UserState.get_share_etf_by_isin)
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

        paper_name = share_etf_info.get("name", "Без названия")

        try:
            last_price = float(share_etf_info.get("last", 0))
            price_text = f"{last_price:.2f}"
        except (ValueError, TypeError):
            price_text = "Нет данных"

        text = (
            f"📈 <b>{paper_name}</b> (<code>{isin_secid}</code>)\n\n"
            f"• <b>Текущая цена:</b> {price_text}.\n"
        )
        await message.answer(text, parse_mode="HTML")

    except Exception as e:
        logging.error(f"Ошибка при получении данных об акции/фонде {isin_secid}: {e}", exc_info=True)  # noqa: G201, LOG015
        await message.answer("Произошла системная ошибка при обработке запроса.")


@router.message(F.text.lower() == "подборка valor")
async def valor_command(message: Message) -> None:
    await message.answer("Пупупупу пока тут пусто...")


# Обработчик команды /delete_token. Удаляет сохраненный токен T-Инвестиций пользователя.
@router.message(Command("delete_token"))
async def delete_token_command(message: Message) -> None:
    user_id = message.from_user.id
    try:
        await requests.delete_user_token(user_id)
        logger.info(f"[User {user_id}] Успешно удалил токен")
        await message.answer("Токен успешно удален!")
    except Exception as e:
        logger.error(f"[User {user_id}] Ошибка при удалении токена: {e}", exc_info=True)  # noqa: G201
        await message.answer("Не удалось удалить токен. Попробуйте позже.")


# Загрузка портфеля по токену
@router.message(Command("set_portfolio_by_token"))
async def set_portfolio_command(message: Message) -> None:
    user_id = message.from_user.id
    logger.info(f"[User {user_id}] Запрос на загрузку портфеля по токену")
    
    try:
        user_token = await requests.get_user_token(user_id)
        if not user_token:
            await message.answer("Сначала необходимо привязать токен с помощью команды /set_token.")
            return

        portfolio = await portfolio_service.get_user_portfolio_token(user_token)
        if not portfolio:
            await message.answer("Не удалось получить данные портфеля. Возможно, портфель пуст или токен недействителен.")
            return
            
        await requests.upload_user_portfolio(portfolio, user_id)
        logger.info(f"[User {user_id}] Портфель успешно загружен по токену")
        await message.answer("Портфель успешно загружен!")
    except Exception as e:
        logger.error(f"[User {user_id}] Ошибка при синхронизации портфеля по токену: {e}", exc_info=True)
        await message.answer("Произошла ошибка при загрузке портфеля.")


@router.message(Command("agreement"))
async def agreement_command(message: Message) -> None:
    await message.answer("https://telegra.ph/Polzovatelskoe-soglashenie-07-29-23")

@router.message(Command("policy"))
async def policy_command(message: Message) -> None:
    await message.answer("https://telegra.ph/Politika-konfidencialnosti-07-29-65")
