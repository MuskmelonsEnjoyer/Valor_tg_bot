import asyncio
import logging

from aiogram import Bot, Dispatcher, html
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

from t_invest import get_all_info, return_portfolio, get_bond_names_map
from agent import agent_answer
from another import clean_text

from config import TELEGRAM_TOKEN, T_INVEST_TOKEN

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot_debug.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

dp = Dispatcher(storage=MemoryStorage())
BONDS_DATA = {}

class UserState(StatesGroup):
    waiting_for_text = State()

# обработчик команды /start
@dp.message(CommandStart())
async def command_start_hendler(message: Message) -> None:
    await message.answer(f"Привет, {html.bold(message.from_user.full_name)}!\nЯ финансовый помощник. Моя основная задача - помогать с брокерским счётом.\nЧтобы узнать, что я умею, введите /info.")

# обработчик команды /info
@dp.message(Command("info"))
async def info_command(message: Message) -> None:
    info_text = (
        "Я могу помочь Вам с информацией о вашем портфеле в Т-Инвестициях и ответить на вопросы по финансовым рынкам.\n\n"
        "Для того, чтобы я мог получить информацию о вашем портфеле, можно:\n\n"
        "1. Отправить API ключ Т-Инвестиций через команду /set_token &ltваш_токен&gt (этот токен можно получить в личном кабинете Т-Инвестиций).\n\n"
        "2. Отправить экспортированный файл портфеля через команду /set_file (файл можно скачать в личном кабинете Т-Инвестиций). (В разработке)\n\n"
        "3. Прислать список ISIN Ваших бумаг через команду /set_bonds &ltтикер1, тикер2,...&gt\nнапример: /set_bonds SBER, GAZP, SU29001RMFS6... (В разработке)\n\n"
        "Доступные команды: /help\n"
    )
    await message.answer(info_text, parse_mode="HTML")

# Обработчик команды /portfolio. Выводит информацию о портфеле пользователя.
@dp.message(Command("portfolio"))
async def return_portfolio_tel(message: Message) -> None:
    format_message = return_portfolio(bonds_names=BONDS_DATA)
    await message.answer(format_message, parse_mode="HTML")

# Обработчик команды /agent. Входит в режим агента финансовой поддержки.
@dp.message(Command("agent"))
async def agent_mode(message: Message, state: FSMContext):
    await message.answer("Введите ваш запрос:")
    await state.set_state(UserState.waiting_for_text)

# Обработчик текстовых сообщений. Передает ввод пользователя агенту и возвращает ответ.
@dp.message(UserState.waiting_for_text)
async def process_text(message: Message, state: FSMContext):
    user_input = clean_text(message.text)
    user_id = message.from_user.id

    logger.info(f"User {user_id} sent request: {user_input[:50]}...")

    wait_msg = await message.answer("Готовлю ответ...")

    try:
        loop = asyncio.get_event_loop()
        answer = await loop.run_in_executor(
            None, 
            agent_answer, 
            user_input,
            user_id, 
            BONDS_DATA)
        
        logger.info(f"Agent response to user {user_id}: {answer[:50]}...")

        await wait_msg.delete()
        await message.answer(answer, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error processing request for user {user_id}: {e}")
        await wait_msg.delete()
        await message.answer("Произошла ошибка при обработке вашего запроса. Пожалуйста, попробуйте позже.")

# Обработчик команды /stop. Выходит из режима агента.
@dp.message(Command("stop"))
async def stop_command(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Режим агента остановлен.")

# Список команд бота
@dp.message(Command("help"))
async def help_command(message: Message) -> None:
    help_text = (
        "Доступные команды:\n"
        "/portfolio - Получить информацию о портфеле\n"
        "/agent - Войти в режим агента финансовой поддержки\n"
        "/stop - Выйти из режима агента\n"
    )
    await message.answer(help_text)

# Главная функция для запуска бота
async def main() ->None:
    print("Запускаем бота...")
    bot = Bot(token=TELEGRAM_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    print("Бот запущен")
    await dp.start_polling(bot)

# await main()
if __name__ == "__main__":
    BONDS_DATA = get_bond_names_map(T_INVEST_TOKEN)
    asyncio.run(main())