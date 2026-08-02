from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Any,
    BigInteger,
    DateTime,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


# Определение таблицы и модели для хранения информации о всех активах
class Instruments(Base):
    __tablename__ = "instruments"
    __table_args__ = (
        {"schema": "public"},
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    secid: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    isin: Mapped[str | None] = mapped_column(String(12), unique=True, nullable=True)
    instrument_type: Mapped[str] = mapped_column("type", String(20), index=True)
    currency: Mapped[str] = mapped_column(String(10))
    extra_data: Mapped[dict[str, Any]] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<Instrument(secid='{self.secid}', type='{self.instrument_type}')>"

# Определение таблицы для хранения API-токенов Т-Инвестиций пользователей
class UserToken(Base):
    __tablename__ = "users_t_invest_tokens"
    __table_args__ = {"schema": "public"}

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_t_invest_token: Mapped[str] = mapped_column(String)


# Определение таблицы хранения портфеля пользователя
class UserPortfolio(Base):
    __tablename__ = "user_portfolio"
    __table_args__ = (
        UniqueConstraint("user_id", "isin", name="uix_user_isin"),
        {"schema": "public"}
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger)
    isin: Mapped[str] = mapped_column(String(12))
    quantity: Mapped[BigInteger] = mapped_column(BigInteger, default=0)
    avg_price: Mapped[Decimal | None] = mapped_column(Numeric(15, 4))
    paper_data: Mapped[dict[str, Any]] = mapped_column(JSONB)


class Bonds(Base):
    __tablename__ = "bonds"
    __table_args__ = {"schema": "public"}

    isin: Mapped[str] = mapped_column(String(12), primary_key=True)
    extra_data: Mapped[dict | None] = mapped_column(JSONB, default=dict)


# Позже доработаю универсальную таблицу для данных по портфелю

# class UserPortfolio(Base):
#     __tablename__ = "user_portfolio"
#     __table_args__ = (
#         # Один и тот же тикер не должен дублироваться у одного юзера.
#         # Вместо дублирования мы должны увеличивать quantity.
#         UniqueConstraint("user_id", "ticker", name="uq_user_ticker"),
#         {"schema": "public"},
#     )

#     id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
#     user_id: Mapped[int] = mapped_column(BigInteger, index=True)
#     ticker: Mapped[str] = mapped_column(String(20), index=True)
#     asset_type: Mapped[str] = mapped_column(String(20))
#     quantity: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=0)
#     average_buy_price: Mapped[Decimal | None] = mapped_column(Numeric(15, 4))
#     extra_data: Mapped[dict | None] = mapped_column(JSONB, default=dict)