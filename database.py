import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, Identity, BigInteger
from sqlalchemy.dialects.postgresql import insert as pg_insert
from config import DATABASE_URL

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

# Определение базы данных и модели для хранения информации о облигациях.
class Bonds(Base):
    __tablename__ = "bonds_list"
    __table_args__ = {'schema': 'public'}

    bond_id = Column(Integer, Identity(start=1), primary_key=True)
    bond_name = Column(String, index=True)
    bond_isin = Column(String, unique=True, index=True)
    source_name = Column(String, index=True)

# Функция загрузки облигаций по API т-инвестиции.
async def update_bonds(bonds_dict: list):
     
    bonds_dict = bonds_dict
    if not bonds_dict:
        return

    prepared_values = [
        {
            "bond_isin": isin, 
            "bond_name": name,
            "source_name": "T-Invest"
        } 
        for isin, name in bonds_dict.items()
    ]

    async with engine.begin() as conn: 

        stmt = pg_insert(Bonds).values(prepared_values)

        upstmt = stmt.on_conflict_do_update(
            index_elements=['bond_isin'],
            set_=dict(
                bond_name=stmt.excluded.bond_name,
                source_name=stmt.excluded.source_name
            )
        )
        await conn.execute(upstmt)

class User_tokens(Base):
    __tablename__ = "users_t_invest_tokens"
    __table_args__ = {'schema': 'public'}

    user_id = Column(BigInteger, primary_key=True, index=True)
    user_t_invest_token = Column(String, nullable=False)

async def save_user_token(user_id: int, token: str) -> None:
    async with AsyncSession(engine) as session:
        stmt = pg_insert(User_tokens).values(user_id=user_id, user_t_invest_token=token)
        upstmt = stmt.on_conflict_do_update(
            index_elements=['user_id'],
            set_=dict(user_t_invest_token=stmt.excluded.user_t_invest_token)
        )
        await session.execute(upstmt)
        await session.commit()