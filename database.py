import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, Identity, BigInteger, select, delete, UniqueConstraint
from sqlalchemy.dialects.postgresql import insert as pg_insert
from config import DATABASE_URL
from sqlalchemy.dialects.postgresql import JSONB
import json

Base = declarative_base()
URL = DATABASE_URL
engine = create_async_engine(URL, echo=False)
# Инициализация базы данных.
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# Функция, которая сработает при старте
async def on_startup():
    print("Инициализация БД...")
    await init_db()
    print("БД готова.")

# Функция, которая сработает при остановке (например, закрыть соединение)
async def on_shutdown():
    print("Закрываем соединение с БД...")
    await engine.dispose()
    print("Соединение с БД закрыто.")

# Определение базы данных и модели для хранения информации о всех активах.
class Instruments(Base):
    __tablename__ = "instruments"
    __table_args__ = (UniqueConstraint('instrument_ticker', 'instrument_class_code', name='uix_ticker_class_code'),
        {'schema': 'public'})

    instrument_id = Column(Integer, Identity(start=1), primary_key=True)
    instrument_name = Column(String, index=True)
    instrument_isin = Column(String(12), unique=True, index=True)
    instrument_uid = Column(String, index=True)
    instrument_ticker = Column(String, index=True)
    instrument_currency = Column(String, index=True)
    instrument_type = Column(String, index=True)
    instrument_class_code = Column(String, index=True)
    instrument_source_id = Column(String, index=True)
    instrument_figi = Column(String, unique=True, index=True)

# Функция загрузки всех активов по API т-инвестиции.
async def update_actives(instrument_list: list[dict]):
    if not instrument_list:
        return

    async with engine.begin() as conn: 
        stmt = pg_insert(Instruments).values(instrument_list)

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

# Определение базы данных для хранения API токенов т-инвестиции пользователей
class User_tokens(Base):
    __tablename__ = "users_t_invest_tokens"
    __table_args__ = {'schema': 'public'}

    user_id = Column(BigInteger, primary_key=True, index=True)
    user_t_invest_token = Column(String, nullable=False)

# Функция сохранения API токенов пользователей
async def save_user_token(user_id: int, token: str) -> None:
    async with AsyncSession(engine) as session:
        stmt = pg_insert(User_tokens).values(user_id=user_id, user_t_invest_token=token)
        upstmt = stmt.on_conflict_do_update(
            index_elements=['user_id'],
            set_=dict(user_t_invest_token=stmt.excluded.user_t_invest_token)
        )
        await session.execute(upstmt)
        await session.commit()

# Функция получения токена пользователя
async def get_user_token(user_id: int) -> str | None:
    async with AsyncSession(engine) as session:
        stmt = select(User_tokens).where(User_tokens.user_id == user_id)

        result = await session.execute(stmt)
        record = result.scalar_one_or_none()

        return record.user_t_invest_token if record else None


#Функция удаления токена пользователя
async def delete_user_token(user_id: int) -> None:
    async with AsyncSession(engine) as session:
        stmt = delete(User_tokens).where(User_tokens.user_id == user_id)
        await session.execute(stmt)
        await session.commit()


# Определение базы данных хранения информации об инструментах
class Hash_all_instruments(Base):
    __tablename__ = "hash_all_instruments"
    __table_args__ = {'schema': 'public'}

    isin = Column(String, primary_key=True, index=True)
    inst_data = Column(JSONB, nullable=False)

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
        stmt = pg_insert(Hash_all_instruments).values(values_to_insert)

        upstmt = stmt.on_conflict_do_update(
            index_elements=['isin'],
            set_=dict(inst_data=stmt.excluded.inst_data)
        )

        await session.execute(upstmt)
        await session.commit()

# Функция поиска данных бумаги по её ISIN
async def find_inst_data(isin: str) -> dict | None:

    async with AsyncSession(engine) as session:
        stmt = select(Hash_all_instruments).where(Hash_all_instruments.isin == isin)

        result = await session.execute(stmt)

        record = result.scalar_one_or_none()

        if record:
            return record.inst_data
        return None

# Определение базы данных хранения портфеля пользователя
class User_portfolio(Base):
    __tablename__ = "user_portfolio"
    __table_args__ = {"schema": "public"}

    user_id = Column(BigInteger, primary_key=True, index=True)
    portfolio_data = Column(JSONB, nullable=False)

# Функция обновления портфеля пользователя
async def upload_user_portfolio(portfolio:dict, user_id:int)->None:
    async with AsyncSession(engine) as session:
        insert_data = {
            "user_id": user_id,
            "portfolio_data": portfolio
        }
        stmt = pg_insert(User_portfolio).values(insert_data)

        upstmt = stmt.on_conflict_do_update(
            index_elements=["user_id"],
            set_=dict(portfolio_data=stmt.excluded.portfolio_data)
        )
        
        await session.execute(upstmt)
        await session.commit()

# Функция поиска названия актива по figi
async def find_name_by_figi(figi: str) -> str | None:
    async with AsyncSession(engine) as session:
        stmt = select(Instruments.instrument_name).where(Instruments.instrument_figi == figi)

        result = await session.execute(stmt)
        record = result.scalar_one_or_none()

        return record
    
# Функция возвращающая портфель
async def get_user_portfolio(user_id: int) -> dict | None:
    async with AsyncSession(engine) as session:
        stmt = select(User_portfolio.portfolio_data).where(User_portfolio.user_id == user_id)

        result = await session.execute(stmt)
        record = result.scalar_one_or_none()

        return record