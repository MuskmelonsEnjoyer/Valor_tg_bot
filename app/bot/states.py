from aiogram.fsm.state import State, StatesGroup

class UserState(StatesGroup):
    waiting_for_text = State()
    waiting_for_token = State()