import asyncio

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

    return result_portfolio


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
