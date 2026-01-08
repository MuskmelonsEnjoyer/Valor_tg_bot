from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert


from app.database.session import engine
import app.database.models as models

# Функция загрузки всех активов по API т-инвестиции.
async def update_actives(instrument_list: list[dict]):
    if not instrument_list:
        return

    async with engine.begin() as conn: 
        stmt = pg_insert(models.Instruments).values(instrument_list)

        upstmt = stmt.on_conflict_do_update(
            constraint="uix_ticker_class_code",
            set_=dict(
                instrument_name=stmt.excluded.instrument_name,
                instrument_isin=stmt.excluded.instrument_isin,
                instrument_uid=stmt.excluded.instrument_uid,
                instrument_currency=stmt.excluded.instrument_currency,
                instrument_source_id=stmt.excluded.instrument_source_id,
                instrument_figi=stmt.excluded.instrument_figi
            )
        )
        await conn.execute(upstmt)

# Функция сохранения API токенов пользователей
async def save_user_token(user_id: int, token: str) -> None:
    async with AsyncSession(engine) as session:
        stmt = pg_insert(models.User_tokens).values(user_id=user_id, user_t_invest_token=token)
        upstmt = stmt.on_conflict_do_update(
            index_elements=['user_id'],
            set_=dict(user_t_invest_token=stmt.excluded.user_t_invest_token)
        )
        await session.execute(upstmt)
        await session.commit()

# Функция получения токена пользователя
async def get_user_token(user_id: int) -> str | None:
    async with AsyncSession(engine) as session:
        stmt = select(models.User_tokens).where(models.User_tokens.user_id == user_id)

        result = await session.execute(stmt)
        record = result.scalar_one_or_none()

        return record.user_t_invest_token if record else None


#Функция удаления токена пользователя
async def delete_user_token(user_id: int) -> None:
    async with AsyncSession(engine) as session:
        stmt = delete(models.User_tokens).where(models.User_tokens.user_id == user_id)
        await session.execute(stmt)
        await session.commit()

# Функция сохранения информации об инструментах в базу данных
async def save_instruments_bulk(instruments_map: dict) -> None:

    if not instruments_map:
        return

    values_to_insert = [
        {
            "isin": isin, 
            "inst_data": data 
        } 
        for isin, data in instruments_map.items()
    ]

    async with AsyncSession(engine) as session:
        stmt = pg_insert(models.Hash_all_instruments).values(values_to_insert)

        upstmt = stmt.on_conflict_do_update(
            index_elements=['isin'],
            set_=dict(inst_data=stmt.excluded.inst_data)
        )

        await session.execute(upstmt)
        await session.commit()

# Функция поиска данных бумаги по её ISIN
async def find_inst_data(isin: str) -> dict | None:

    async with AsyncSession(engine) as session:
        stmt = select(models.Hash_all_instruments).where(models.Hash_all_instruments.isin == isin)
        result = await session.execute(stmt)
        record = result.scalar_one_or_none()

        if record:
            return record.inst_data
        return None

# Функция обновления портфеля пользователя
async def upload_user_portfolio(portfolio:dict, user_id:int)->None:
    async with AsyncSession(engine) as session:
        insert_data = {
            "user_id": user_id,
            "portfolio_data": portfolio
        }
        stmt = pg_insert(models.User_portfolio).values(insert_data)

        upstmt = stmt.on_conflict_do_update(
            index_elements=["user_id"],
            set_=dict(portfolio_data=stmt.excluded.portfolio_data)
        )
        
        await session.execute(upstmt)
        await session.commit()

# Функция поиска названия актива по figi
async def find_name_by_figi(figi: str) -> str | None:
    async with AsyncSession(engine) as session:
        stmt = select(models.Instruments.instrument_name).where(models.Instruments.instrument_figi == figi)

        result = await session.execute(stmt)
        record = result.scalar_one_or_none()

        return record
    
# Функция возвращающая портфель
async def get_user_portfolio(user_id: int) -> dict | None:
    async with AsyncSession(engine) as session:
        stmt = select(models.User_portfolio.portfolio_data).where(models.User_portfolio.user_id == user_id)

        result = await session.execute(stmt)
        record = result.scalar_one_or_none()

        return record