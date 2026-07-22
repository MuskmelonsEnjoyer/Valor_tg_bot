from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram import html, Router
from t_tech.invest import AsyncClient, RequestError
from aiogram.enums import ChatAction

import app.database.requests as requests
# import app.agent.agent as agent
import app.utils.formatting as formatting
import app.services.portfolio_servise as portfolio_service

from app.bot import states
import logging

router = Router()

logger = logging.getLogger("handlers")

# обработчик команды /start
@router.message(CommandStart())
async def command_start_hendler(message: Message) -> None:
    await message.answer(
        f"Привет, {html.bold(message.from_user.full_name)}!\nЯ финансовый помощник. Моя основная задача - помогать с брокерским счётом.\nЧтобы узнать, что я умею, введите /info."
    )

# обработчик команды /info
@router.message(Command("info"))
async def info_command(message: Message) -> None:
    info_text = (
        "Я могу помочь Вам с информацией о вашем портфеле в Т-Инвестициях и ответить на вопросы по финансовым рынкам.\n\n"
        "Для того, чтобы я мог получить информацию о вашем портфеле, можно:\n\n"
        "1. Отправить API ключ Т-Инвестиций через команду /set_token &ltваш_токен&gt (этот токен можно получить в личном кабинете Т-Инвестиций),\n\n"
        "2. Отправить экспортированный файл портфеля через команду /set_file (файл можно скачать в личном кабинете Т-Инвестиций). (В разработке),\n\n"
        "3. Прислать список ISIN Ваших бумаг через команду /set_actives &ltтикер1, тикер2,...&gt\nнапример: /set_actives SBER, GAZP, SU29001RMFS6... (В разработке).\n\n"
        "4. Получить данные облигаций по ISIN через команду /get_bond_info"
        "Доступные команды: /help\n"
    )
    await message.answer(info_text, parse_mode="HTML")


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

    try:
        async with AsyncClient(token=token) as client:
            await client.users.get_accounts()
            await requests.save_user_token(user_id, token)
            await message.delete()
            await state.clear()
        return await message.answer("Токен успешно сохранен!")

    except RequestError:
        await message.delete()
        await message.answer("Ваш токен нейдействителен")
        await state.clear()

    except Exception:
        await message.delete()
        await message.answer(
            "Произошла ошибка при сохранении вашего токена. Пожалуйста, попробуйте позже."
        )
        await state.clear()

# Обработчик команды /get_bond_info. Предоставляет информацию облигации по её ISIN
@router.message(Command("get_bond_info"))
async def get_bond_info(message: Message, state: FSMContext) -> None:
    await message.answer("Отправьте ISIN облигации")
    await state.set_state(states.UserState.waiting_for_text)


# Обработчик получения токена от пользователя.
@router.message(states.UserState.waiting_for_text)
async def process_bond_info(message: Message, state: FSMContext):

    isin = message.text.strip().upper()
    await state.clear()

    try:
        bond_info = await requests.get_bonds_info(isin)

        if not bond_info:
            await message.answer("Облигация с таким ISIN не найдена.")
            return

        bond_name = bond_info.get("bond_name", "Без названия")
        prevprice = bond_info.get("prevprice")
        accruedint = bond_info.get("accruedint", 0)
        face_value = bond_info.get("face_value", 0)
        coupon_value = bond_info.get("coupon_value", 0)
        coupon_period = bond_info.get("coupon_period", 0)
        coupon_prercent = bond_info.get("coupon_prercent", 0)

        matdate = bond_info.get("matdate", "Н/Д")
        next_coupon = bond_info.get("next_coupon", "Н/Д")

        text = (
            f"📈 <b>{bond_name}</b> (<code>{isin}</code>)\n\n"
            f"• <b>Номинал:</b> {face_value} руб.\n"
            f"• <b>Купон:</b> {coupon_value} руб. ({coupon_prercent:.2f}%)\n"
            f"• <b>Купонные выплаты в год:</b> {round(365/coupon_period)}\n"
            f"• <b>НКД:</b> {accruedint} руб.\n"
            f"• <b>Текущая цена:</b> {prevprice} руб.\n"
            f"• <b>Следующий купон:</b> {formatting.format_date(next_coupon)}\n"
            f"• <b>Дата погашения:</b> {formatting.format_date(matdate)}"
        )
        await message.answer(text, parse_mode="HTML")

    except Exception as e:
        logging.error(f"Ошибка при получении данных об облигации {isin}: {e}", exc_info=True)
        await message.answer("Произошла системная ошибка при обработке запроса.")


# Обработчик команды /delete_token. Удаляет сохраненный токен T-Инвестиций пользователя.
@router.message(Command("delete_token"))
async def delete_token_command(message: Message) -> None:
    user_id = message.from_user.id
    await requests.delete_user_token(user_id)
    await message.answer("Токен успешно удален!")


@router.message(Command("set_portfolio_by_token"))
async def set_portfolio_command(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    user_token = await requests.get_user_token(user_id)
    portfolio = await portfolio_service.get_user_portfolio_token(user_token)
    await requests.upload_user_portfolio(portfolio, user_id)


# Обработчик команды /agent. Входит в режим агента финансовой поддержки.
# @router.message(Command("agent"))
# async def agent_mode(message: Message, state: FSMContext):
#     await message.answer("Введите ваш запрос:")
#     await state.set_state(states.UserState.waiting_for_text)


# Обработчик текстовых сообщений. Передает ввод пользователя агенту и возвращает ответ.
# @router.message(states.UserState.waiting_for_text)
# async def process_text(message: Message, state: FSMContext):
#     user_input = formatting.clean_text(message.text)
#     user_id = message.from_user.id

#     await message.bot.send_chat_action(
#         chat_id=message.chat.id, action=ChatAction.TYPING
#     )

#     try:
#         answer = await agent.agent_answer(user_input, user_id)

#         await message.answer(answer, parse_mode="HTML")
#     except Exception as e:
#         logger.error(f"Ошибка в работе агента: {e}")
#         await message.answer(
#             "Произошла ошибка при обработке вашего запроса. Пожалуйста, попробуйте позже."
#         )


# # Обработчик команды /stop. Выходит из режима агента.
# @router.message(Command("stop"))
# async def stop_command(message: Message, state: FSMContext):
#     await state.clear()
#     await message.answer("Режим агента остановлен.")


# Список команд бота
@router.message(Command("help"))
async def help_command(message: Message) -> None:
    help_text = (
        "Доступные команды:\n"
        "/get_bond_info - Получить информацию по облигации"
        "/portfolio - Получить информацию о портфеле. (В разработке).\n"
        "/delete_token - Удалить токен.\n"
        # "/agent - Войти в режим агента финансовой поддержки.\n"
        # "/stop - Выйти из режима агента.\n"
        "/set_portfolio_by_token.\n"
        "/set_portfolio_by_xlxs. (В разработке).\n"
    )
    await message.answer(help_text)
