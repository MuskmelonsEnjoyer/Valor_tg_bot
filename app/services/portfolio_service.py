from t_tech.invest import AsyncClient
from t_tech.invest.utils import quotation_to_decimal, money_to_decimal


async def process_portfolio(client: AsyncClient, account_id: str) -> tuple:
    """
    Функция для получения информации об активах клиента.
    """
    portfolio = await client.operations.get_portfolio(account_id=account_id)

    total_val = money_to_decimal(portfolio.total_amount_portfolio)
    currency = portfolio.total_amount_portfolio.currency

    positions_list = []
    for pos in portfolio.positions:
        positions_list.append(
            {
                "Тикер": pos.ticker,
                "Тип": pos.instrument_type,
                "Количество": quotation_to_decimal(pos.quantity),
                "Цена": money_to_decimal(pos.current_price),
                # "Валюта": pos.current_price.currency
            }
        )

    return total_val, currency, positions_list


async def get_all_info(token: str) -> list[dict]:
    """
    Функция для получения информации на всех счетах клиента.
    """
    result_data = []
    async with AsyncClient(token) as client:
        accounts_resp = await client.users.get_accounts()

        for account in accounts_resp.accounts:
            # print(f"Обработка счета: {account.name} ({account.id})...")

            (
                total_val,
                currency,
                positions,
            ) = await process_portfolio(client, account.id)

            account_info = {
                "account_name": account.name,
                # "account_id": account.id,
                # "total_value": total_val,
                "currency": currency,
                "positions": positions,
            }
            result_data.append(account_info)
    return result_data


async def get_user_portfolio_token(token: str):
    """
    Получает портфель через API по токену
    """
    async with AsyncClient(token) as client:
        info = await client.users.get_accounts()
        positions_by_secid = {}

        for account in info.accounts:
            portfolio = await client.operations.get_portfolio(account_id=account.id)
            if len(portfolio.positions) > 0:
                for pos in portfolio.positions:
                    quantity = quotation_to_decimal(pos.quantity)
                    avg_price = money_to_decimal(pos.average_position_price)
                    current = positions_by_secid.get(pos.ticker)
                    if current is None:
                        positions_by_secid[pos.ticker] = {
                            "secid": pos.ticker,
                            "avg_price": avg_price,
                            "quantity": quantity,
                        }
                        continue

                    total_quantity = current["quantity"] + quantity
                    current["avg_price"] = (
                        current["avg_price"] * current["quantity"]
                        + avg_price * quantity
                    ) / total_quantity
                    current["quantity"] = total_quantity

    return list(positions_by_secid.values())
