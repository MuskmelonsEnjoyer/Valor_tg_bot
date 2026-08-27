import asyncio
<<<<<<< HEAD
import openpyxl
from app.services.t_invest import find_current_price
import app.database.requests as requests


async def get_user_portfolio_xlxs(file_name: str, token: str):
    loop = asyncio.get_running_loop()

    wb = await loop.run_in_executor(None, openpyxl.load_workbook, file_name)
    ws = wb.active

    all_rows = list(ws.values)

    user_actives = await find_quantity(all_rows)

    result_portfolio = []
    token = token

    for i in user_actives:
        isin = i.get("isin")
        inst_data = await requests.find_inst_data(isin)
        figi = inst_data.get("figi")
        current_price = await find_current_price(figi, token)

        portfolio_item = {
            "name": i.get("name"),
            "quantity": i.get("reminder"),
            "current_price": current_price,
        }
        result_portfolio.append(portfolio_item)
=======

import app.database.requests as requests
import openpyxl
from app.services.t_invest import find_current_price


def _read_rows(file_name: str) -> list[tuple]:
    workbook = openpyxl.load_workbook(file_name, read_only=True, data_only=True)
    try:
        return list(workbook.active.values)
    finally:
        workbook.close()


async def get_user_portfolio_xlsx(file_name: str, token: str) -> list[dict]:
    all_rows = await asyncio.to_thread(_read_rows, file_name)
    user_assets = await find_quantity(all_rows)

    result_portfolio = []
    for asset in user_assets:
        isin = asset["isin"]
        instrument = await requests.find_inst_data(isin)
        if instrument is None:
            continue

        figi = instrument.get("figi")
        current_price = (
            await find_current_price(figi, token)
            if figi
            else instrument.get("last_price", instrument.get("last"))
        )
        result_portfolio.append(
            {
                "name": asset["name"],
                "secid": instrument["secid"],
                "isin": isin,
                "quantity": asset["quantity"],
                "current_price": current_price,
            }
        )
>>>>>>> f04103d (version 1.0.0)

    return result_portfolio


<<<<<<< HEAD
async def find_quantity(all_rows: list) -> list:
    """
    Парсинг данных из excel файла пользователя. Основная информация по бумагам находится в пункте 3.1
    Получем список словарей, которые содержат: название, тикер, isin, остаток бумаг на момент выгрузки. Если остаток = 0, значит бумаг нет в портфеле.
    """
    start_index = None
    end_index = None

    for i in range(len(all_rows)):
        if ("3.1 Движение по ценным бумагам инвестора") in all_rows[i]:
            start_index = i + 1
        if ("3.2 Движение по производным финансовым инструментам") in all_rows[i]:
            end_index = i - 1

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
                            "name": name,
                            "ticker": code,
                            "isin": isin,
                            "reminder": reminder,
                        }
                        full_data.append(item)

            except TypeError:
                continue
    return full_data
=======
async def find_quantity(all_rows: list[tuple]) -> list[dict]:
    """Extract non-zero securities from sections 3.1-3.2 of a broker report."""
    start_index = None
    end_index = None

    for index, row in enumerate(all_rows):
        if "3.1 Движение по ценным бумагам инвестора" in row:
            start_index = index + 1
        if "3.2 Движение по производным финансовым инструментам" in row:
            end_index = index

    if start_index is None or end_index is None or start_index >= end_index:
        raise ValueError("Не удалось найти разделы 3.1 и 3.2 в Excel-отчете")

    assets = []
    for row in all_rows[start_index:end_index]:
        if len(row) <= 8:
            continue

        quantity = row[8]
        if (
            not isinstance(quantity, (int, float))
            or isinstance(quantity, bool)
            or quantity < 1
        ):
            continue

        if not all(row[index] for index in (0, 1, 2)):
            continue

        assets.append(
            {
                "name": row[0],
                "ticker": row[1],
                "isin": row[2],
                "quantity": quantity,
            }
        )

    return assets
>>>>>>> f04103d (version 1.0.0)
