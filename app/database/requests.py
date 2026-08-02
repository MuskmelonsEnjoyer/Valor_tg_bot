from app.database import models
from app.database.session import engine
from app.services.api_moex import parsing_instruments
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession


# Функция сохранения API токенов пользователей
async def save_user_token(user_id: int, token: str) -> None:
    async with AsyncSession(engine) as session:
        stmt = pg_insert(models.User_tokens).values(
            user_id=user_id, user_t_invest_token=token
        )
        upstmt = stmt.on_conflict_do_update(
            index_elements=["user_id"],
            set_={"user_t_invest_token": stmt.excluded.user_t_invest_token},
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


# Функция удаления токена пользователя
async def delete_user_token(user_id: int) -> None:
    async with AsyncSession(engine) as session:
        stmt = delete(models.User_tokens).where(models.User_tokens.user_id == user_id)
        await session.execute(stmt)
        await session.commit()


# Функция добавления бумаги в портфель пользователем
async def upload_user_portfolio(user_id: int, secid: str, avg_price: float, quantity: int) -> None:
    async with AsyncSession(engine) as session:
        
        paper = select(models.Instruments.extra_data).where((models.Instruments.secid == secid) | (models.Instruments.isin == secid))

        result = await session.execute(paper)
        paper_data = result.scalar() 
        
        if not paper_data:
            return False 
        
        insert_data = {"user_id": user_id, "isin": secid, "paper_data": paper_data, "avg_price": avg_price, "quantity": quantity}
        
        stmt = pg_insert(models.UserPortfolio).values(insert_data)

        upstmt = stmt.on_conflict_do_update(
            index_elements=["user_id", "isin"],
            set_={"paper_data": stmt.excluded.paper_data, "avg_price": stmt.excluded.avg_price, "quantity": stmt.excluded.quantity} 
        )

        await session.execute(upstmt)
        await session.commit()
        
        return True

# Функция удаления бумаги в портфель пользователем
async def drop_isin_portfolio(user_id: int, secid: str) -> None:
    async with AsyncSession(engine) as session:
        stmt = (
            delete(models.UserPortfolio).where(
            models.UserPortfolio.user_id == user_id,
            models.UserPortfolio.isin == secid
            )
        )

        result = await session.execute(stmt)
        await session.commit()
        
        return result.rowcount > 0


# Функция удаления бумаги в портфель пользователем
async def drop_user_portfolio(user_id: int) -> None:
    async with AsyncSession(engine) as session:
        stmt = (delete(models.UserPortfolio).where(models.UserPortfolio.user_id == user_id))

        result = await session.execute(stmt)
        await session.commit()
        
        return result.rowcount > 0


# Функция возвращающая портфель
async def get_user_portfolio(user_id: int) -> list[dict]:
    async with AsyncSession(engine) as session:
        stmt = select(models.UserPortfolio).where(
            models.UserPortfolio.user_id == user_id
        )
        result = await session.execute(stmt)
        records = result.scalars().all()

        portfolio = []
        for record in records:
            paper = dict(record.paper_data) if record.paper_data else {}
            
            paper["isin"] = record.isin
            paper["avg_price"] = getattr(record, "avg_price", None)
            paper["quantity"] = getattr(record, "quantity", None)

            portfolio.append(paper)

        return portfolio

# Функция заполнения БД бондов
async def upload_bonds_data() -> None:
    async with AsyncSession(engine) as session:

        bonds = await parsing_instruments()

        insert_data = [
        {"isin": isin, "extra_data": extra_data}
        for isin, extra_data in bonds.items()
    ]

    async with AsyncSession(engine) as session:

        stmt = pg_insert(models.Bonds).values(insert_data)

        upsert_stmt = stmt.on_conflict_do_update(
            index_elements=["isin"],
            set_={"extra_data": stmt.excluded.extra_data}
        )

        await session.execute(upsert_stmt)
        await session.commit()


# Функция заполнения таблицы всех инструментов
async def upload_bonds_shares() -> None:
        
    shares, bonds = await parsing_instruments()

    insert_data = []

    for secid, data in bonds.items():
        insert_data.append({
            "secid": secid,
            "isin": data.get("isin"),
            "instrument_type": "bond",
            "currency": data.get("currency", "RUB"),
            "extra_data": data,
        })

    for secid, data in shares.items():
        insert_data.append({
            "secid": secid,
            "isin": data.get("isin"),
            "instrument_type": "share",
            "currency": data.get("currency", "RUB"),
            "extra_data": data,
        })

    async with AsyncSession(engine) as session:
        stmt = pg_insert(models.Instruments).values(insert_data)

        upsert_stmt = stmt.on_conflict_do_update(
            index_elements=["secid"],
            set_={
                "isin": stmt.excluded.isin,
                "currency": stmt.excluded.currency,
                "extra_data": stmt.excluded.extra_data,
                "updated_at": func.now(),
            },
        )

        await session.execute(upsert_stmt)
        await session.commit()


# Функция получения данных облигации из таблицы
async def get_bonds_info(isin: str) -> dict | None:
    async with AsyncSession(engine) as session:
        stmt = select(models.Instruments.extra_data).where(
            ((models.Instruments.isin == isin) | (models.Instruments.secid == isin)),
            models.Instruments.instrument_type == "bond",
        )

        result = await session.execute(stmt)
        record = result.scalar_one_or_none()

        return record

# Функция получения данных облигации из таблицы
async def get_share_etf_info(isin_secid: str) -> dict | None:
    async with AsyncSession(engine) as session:
        stmt = select(models.Instruments.extra_data).where(
            ((models.Instruments.secid == isin_secid) | (models.Instruments.isin == isin_secid)),
            models.Instruments.instrument_type == "share",
        )

        result = await session.execute(stmt)
        record = result.scalar_one_or_none()

        return record