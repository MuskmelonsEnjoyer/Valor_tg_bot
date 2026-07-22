from decimal import Decimal
from sqlalchemy import BigInteger, Numeric, String, UniqueConstraint, Date, Any, Identity
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass


# Определение таблицы и модели для хранения информации о всех активах
class Instrument(Base):
    __tablename__ = "instruments"
    __table_args__ = (
        UniqueConstraint(
            "instrument_ticker", "instrument_class_code", name="uix_ticker_class_code"
        ),
        {"schema": "public"},
    )
    instrument_id: Mapped[int] = mapped_column(Identity(start=1), primary_key=True)
    instrument_name: Mapped[str] = mapped_column(String, index=True)
    instrument_isin: Mapped[str | None] = mapped_column(String(12), unique=True)
    instrument_uid: Mapped[str] = mapped_column(String, index=True)
    instrument_ticker: Mapped[str] = mapped_column(String, index=True)
    instrument_currency: Mapped[str] = mapped_column(String, index=True)
    instrument_type: Mapped[str] = mapped_column(String, index=True)
    instrument_class_code: Mapped[str] = mapped_column(String, index=True)
    instrument_source_id: Mapped[str] = mapped_column(String, index=True)
    instrument_figi: Mapped[str | None] = mapped_column(String, unique=True)


# Определение таблицы для хранения API-токенов Т-Инвестиций пользователей
class UserToken(Base):
    __tablename__ = "users_t_invest_tokens"
    __table_args__ = {"schema": "public"}

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_t_invest_token: Mapped[str] = mapped_column(String)


# Определение таблицы хранения информации об инструментах
class HashAllInstrument(Base):
    __tablename__ = "hash_all_instruments"
    __table_args__ = {"schema": "public"}

    isin: Mapped[str] = mapped_column(String(12), primary_key=True)
    inst_data: Mapped[dict[str, Any]] = mapped_column(JSONB)


# Определение таблицы хранения портфеля пользователя
class UserPortfolio(Base):
    __tablename__ = "user_portfolio"
    __table_args__ = {"schema": "public"}

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    portfolio_data: Mapped[dict[str, Any]] = mapped_column(JSONB)


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