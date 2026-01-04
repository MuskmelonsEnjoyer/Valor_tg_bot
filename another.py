import re
import openpyxl
import functools
import asyncio
from t_invest import find_quantity, find_current_price
from database import find_inst_data, find_name_by_figi
from config import T_INVEST_TOKEN as token
from t_tech.invest import AsyncClient
from t_tech.invest.utils import money_to_decimal, quotation_to_decimal

token = token

def clean_text(text: str) -> str:

    replacements = {
        r"<br\s*/?>": "\n",        # <br> или <br/> -> новая строка
        r"</div>": "\n",           # конец блока -> новая строка
        r"</p>": "\n",             # конец параграфа -> новая строка
        r"<li>": "•",             # элемент списка -> буллит
        r"</li>": "\n",            # конец элемента списка -> новая строка
        r"<ul>": "\n",             # начало списка -> отступ
        r"</ul>": "\n",            # конец списка -> отступ
    }
    
    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    allowed_tags = r"(b|strong|i|em|u|ins|s|strike|del|code|pre|a)"

    clean_text = re.sub(r"</?(?!" + allowed_tags + r"\b)[^>]*>", "", text)

    clean_text = re.sub(r"\n{3,}", "\n\n", clean_text)
    
    return clean_text.strip()

# Функция для парсинга данных о портфеле пользователя из брокерского отчёта в excel формате.
async def get_user_portfolio_xlxs(file_name:str, token:str):
        
        loop = asyncio.get_running_loop()

        wb = await loop.run_in_executor(None, openpyxl.load_workbook, file_name)
        ws = wb.active

        all_rows = list(ws.values)

        user_actives = await find_quantity(all_rows)

        result_portfolio = []
        token = token

        for i in user_actives:

            isin = i.get("isin")
            inst_data = await find_inst_data(isin)
            figi = inst_data.get("figi")
            current_price = await find_current_price(figi, token)

            portfolio_item = {
                "name": i.get("name"),
                "quantity": i.get("reminder"),
                "current_price": current_price
            }
            result_portfolio.append(portfolio_item)
            
        return result_portfolio

async def get_user_portfolio_token(token:str):
    async with AsyncClient(token) as client:
        info = await client.users.get_accounts()
    
        data = []

        for account in info.accounts:
            portfolio = await client.operations.get_portfolio(account_id=account.id)
            if len(portfolio.positions) > 0:
                for pos in portfolio.positions:
                    # current_nkd = money_to_decimal(pos.current_nkd) #накопленный нкд
                    # average_position_price = money_to_decimal(pos.average_position_price_fifo) средняя цена покупки
                    # expected_yield_fifo = money_to_decimal(pos.expected_yield_fifo) изменение за всё время
                    # daily_yield = money_to_decimal(pos.daily_yield) изменение за день
                    figi = pos.figi
                    current_price = money_to_decimal(pos.current_price)
                    name = await find_name_by_figi(figi)
                    quantity = quotation_to_decimal(pos.quantity)
                    result = {
                        "name": name,
                        "current_price": float(current_price),
                        "quantity":float(quantity) 
                    }
                    data.append(result)
    return data