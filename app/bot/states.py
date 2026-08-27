from aiogram.fsm.state import State, StatesGroup


class UserState(StatesGroup):
    waiting_for_text = State()
    search_instrument = State()
    add_selected_instrument = State()
    get_bond_by_isin = State()
    get_share_etf_by_isin = State()
    add_paper_by_isin = State()
    delete_paper_by_isin = State()
    delete_portfolio = State()
    waiting_for_token = State()
    valor_search = State()
    valor_add_position = State()
