from t_tech.invest import Client
from t_tech.invest.utils import quotation_to_decimal, money_to_decimal

from decimal import Decimal

def format_money(value: Decimal) -> str:
    # Форматирует: 12345.678 -> "12 345.68"
    return f"{value:,.2f}".replace(",", " ")

def get_bond_names_map(token: str) -> dict:
    """Создает словарь {isin: name} для всех облигаций в Т-Инвестициях"""
    with Client(token) as client:
        print("Загрузка справочника облигаций...")
        instruments = client.instruments.bonds()
    return {b.isin: b.name for b in instruments.instruments}

def process_portfolio(client: Client, account_id: str) -> tuple:
    """
    Функция для получения информации об активах клиента.
    """
    portfolio = client.operations.get_portfolio(account_id=account_id)

    total_val = money_to_decimal(portfolio.total_amount_portfolio)
    currency = portfolio.total_amount_portfolio.currency
    
    positions_list = []
    for pos in portfolio.positions:
        
        positions_list.append({
            "Тикер": pos.ticker,
            "Тип": pos.instrument_type,
            "Количество": quotation_to_decimal(pos.quantity),
            "Цена": money_to_decimal(pos.current_price),
            #"Валюта": pos.current_price.currency
        })
        
    return total_val, currency, positions_list

def get_all_info(token: str) -> tuple:
    """
    Функция для получения информации на всех счетах клиента.
    """
    result_data = []
    total_cost_list = []
    with Client(token) as client:
        accounts_resp = client.users.get_accounts()
        
        for account in accounts_resp.accounts:
            #print(f"Обработка счета: {account.name} ({account.id})...")
            
            total_val, currency, positions, = process_portfolio(client, account.id)
            
            account_info = {
                "account_name": account.name,
                #"account_id": account.id,
                #"total_value": total_val,
                #"currency": currency,
                "positions": positions
            }
            result_data.append(account_info)
            if currency == "rub":
                total_cost_list.append(total_val)
        total_cost = sum(total_cost_list)    

    return result_data, total_cost

# Форматированный вывод информации о портфеле пользователя
def return_portfolio(bonds_names: dict, token: str) -> str:
    lines = []
    lines.append("💼 <b>Ваш портфель</b>")
    lines.append("")

    data = get_all_info(token)

    for idx, account in enumerate(data[0]):
        positions = account.get('positions', [])
        names = account.get('account_name', [])
        if not positions:
            continue
            
        lines.append(f"📂 <i>Счет {names}</i>")
        
        for pos in positions:
            ticker = pos['Тикер']
            instrument_type = pos['Тип']
            qty = pos['Количество']
            price = pos['Цена']
            total = qty * price

            if instrument_type == "bond":
                bond_name = bonds_names.get(ticker, "Неизвестная облигация")
                lines.append(f"🔹 <b>{bond_name}</b>: {format_money(qty)} шт × {format_money(price)} = <b>{format_money(total)}</b>")
            else:
                lines.append(f"🔹 <b>{ticker}</b>: {format_money(qty)} шт × {format_money(price)} = <b>{format_money(total)}</b>")
        
        lines.append("")

    lines.append(f"💰 <b>Всего: {format_money(data[1])} RUB</b>")

    format_message = "\n".join(lines)

    return format_message