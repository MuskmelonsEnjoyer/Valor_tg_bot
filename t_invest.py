from t_tech.invest import AsyncClient, Client, InstrumentStatus, InstrumentIdType
from t_tech.invest.utils import quotation_to_decimal, money_to_decimal

from decimal import Decimal

def format_money(value: Decimal) -> str:
    # Форматирует: 12345.678 -> "12 345.68"
    return f"{value:,.2f}".replace(",", " ")

async def process_portfolio(client: Client, account_id: str) -> tuple:
    """
    Функция для получения информации об активах клиента.
    """
    portfolio = await client.operations.get_portfolio(account_id=account_id)

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

async def get_all_info(token: str) -> tuple:
    """
    Функция для получения информации на всех счетах клиента.
    """
    result_data = []
    total_cost_list = []
    async with AsyncClient(token) as client:
        accounts_resp = await client.users.get_accounts()
        
        for account in accounts_resp.accounts:
            #print(f"Обработка счета: {account.name} ({account.id})...")
            
            total_val, currency, positions, = await process_portfolio(client, account.id)
            
            account_info = {
                "account_name": account.name,
                #"account_id": account.id,
                #"total_value": total_val,
                "currency": currency,
                "positions": positions
            }
            result_data.append(account_info)
            if currency == "rub":
                total_cost_list.append(total_val)
        total_cost = sum(total_cost_list)

    return result_data

# Форматированный вывод информации о портфеле пользователя
# def return_portfolio(bonds_names: dict, token: str) -> str:
#     lines = []
#     lines.append("💼 <b>Ваш портфель</b>")
#     lines.append("")

#     data = get_all_info(token)

#     for idx, account in enumerate(data[0]):
#         positions = account.get('positions', [])
#         names = account.get('account_name', [])
#         if not positions:
#             continue
            
#         lines.append(f"📂 <i>Счет {names}</i>")
        
#         for pos in positions:
#             ticker = pos['Тикер']
#             instrument_type = pos['Тип']
#             qty = pos['Количество']
#             price = pos['Цена']
#             total = qty * price

#             if instrument_type == "bond":
#                 bond_name = bonds_names.get(ticker, "Неизвестная облигация")
#                 lines.append(f"🔹 <b>{bond_name}</b>: {format_money(qty)} шт × {format_money(price)} = <b>{format_money(total)}</b>")
#             else:
#                 lines.append(f"🔹 <b>{ticker}</b>: {format_money(qty)} шт × {format_money(price)} = <b>{format_money(total)}</b>")
        
#         lines.append("")

#     lines.append(f"💰 <b>Всего: {format_money(data[1])} RUB</b>")

#     format_message = "\n".join(lines)

#     return format_message

# Функция загрузки всех инструментов в базу данных
async def get_all_instruments_list(token: str) -> list[dict]:
    async with AsyncClient(token) as client:
        shares = (await client.instruments.shares(instrument_status=InstrumentStatus.INSTRUMENT_STATUS_BASE)).instruments
        bonds = (await client.instruments.bonds(instrument_status=InstrumentStatus.INSTRUMENT_STATUS_BASE)).instruments
        etfs = (await client.instruments.etfs(instrument_status=InstrumentStatus.INSTRUMENT_STATUS_BASE)).instruments
        
    result_list = []

    def pack_data(items, instrument_type):
        for item in items:
            result_list.append({
                "instrument_name": item.name, 
                "instrument_uid": item.uid,   
                "instrument_ticker": item.ticker,
                "instrument_source_id": instrument_type,
                "instrument_figi": item.figi,
                "instrument_isin": item.isin,
                "instrument_currency": item.currency,
                "instrument_class_code": item.class_code,
                "instrument_source_id": "T-invest"
            })

    pack_data(shares, "share")
    pack_data(bonds, "bond")
    pack_data(etfs, "etf")
        
    return result_list

# Функция для получения данных из xlxs файла пользователя
async def find_quantity(all_rows:list)->list:
    """
    Парсинг данных из excel файла пользователя. Основная информация по бумагам находится в пункте 3.1
    Получем список словарей, которые содержат: название, тикер, isin, остаток бумаг на момент выгрузки. Если остаток = 0, значит бумаг нет в портфеле.
    """
    start_index = None
    end_index = None

    for i in range(len(all_rows)):
        if ("3.1 Движение по ценным бумагам инвестора") in all_rows[i]:
            start_index = i+1
        if ("3.2 Движение по производным финансовым инструментам") in all_rows[i]:
            end_index = i-1
    
    result = all_rows[start_index:end_index]

    data = []

    for i in range(len(result)):
        info = [item for item in result[i] if item is not None]
        data.append(info)
    
    full_data = []

    for row in data:
        if len(row) > 2 and row[8] is not None:
            try:
                if type(row[8]) == float:
                    name = row[0]
                    code = row[1]
                    isin = row[2]
                    reminder = row[8]
                    if reminder >= 1:
                        item = {
                            "name":name,
                            "ticker":code,
                            "isin":isin,
                            "reminder":reminder 
                        }
                        full_data.append(item)

            except TypeError:
                continue
    return full_data

# Функция похожа на предыдущую, содержит только основную информацию по бумагам
# def find_active(all_rows:list)->list:

#     start_index = None
#     end_index = None

#     for i in range(len(all_rows)):
#         if ('4.1 Информация о ценных бумагах') in all_rows[i]:
#             start_index = i+1
#         if ('4.2 Информация о производных финансовых инструментах') in all_rows[i]:
#             end_index = i-1

#     result = all_rows[start_index:end_index]

#     data = []

#     for i in range(len(result)):
#         info = [item for item in result[i] if item is not None]
#         data.append(info)

#     full_data = []

#     for row in data:
#         if len(row) > 2 and row[2] is not None:
#             try:
#                 if len(row[2]) == 12:
#                     name = row[0]
#                     code = row[1]
#                     isin = row[2]

#                     item = {
#                         "name": name,
#                         "code": code,
#                         "isin": isin
#                     }
#                     full_data.append(item)
#             except TypeError:
#                 continue

#     return full_data
# Функция для определения цены актива 
async def find_current_price(figi: str, token:str) -> float | None:
    async with AsyncClient(token) as client:
        try:
            instrument_response = await client.instruments.get_instrument_by(
                id_type=InstrumentIdType.INSTRUMENT_ID_TYPE_FIGI, 
                id=figi
            )
            instrument_uid = instrument_response.instrument.uid
            price_response = await client.market_data.get_last_prices(instrument_id=[instrument_uid])

            if price_response.last_prices:
                price_obj = price_response.last_prices[0].price
                current_price = quotation_to_decimal(price_obj)
                if instrument_response.instrument.instrument_type == 'bond':
                    real_price = (current_price * 10)
                    return float(real_price)
                return float(current_price)
            else:
                print("Цена не найдена (нет данных о торгах)")
                return None

        except Exception as e:
            print(f"Ошибка при запросе: {e}")
            return None