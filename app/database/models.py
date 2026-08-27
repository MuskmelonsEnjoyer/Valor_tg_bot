from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class AppUser(Base):
    __tablename__ = "app_users"
    __table_args__ = {"schema": "public"}

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# Определение таблицы и модели для хранения информации о всех активах
class Instruments(Base):
    __tablename__ = "instruments"
    __table_args__ = {"schema": "public"}
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    secid: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    isin: Mapped[str | None] = mapped_column(String(12), unique=True, nullable=True)
    instrument_type: Mapped[str] = mapped_column("type", String(20), index=True)
    currency: Mapped[str] = mapped_column(String(10))
    extra_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
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

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("public.app_users.user_id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_t_invest_token: Mapped[str] = mapped_column(String, nullable=False)


# Определение таблицы хранения портфеля пользователя
class UserPortfolio(Base):
    __tablename__ = "user_portfolio"
    __table_args__ = (
        UniqueConstraint("user_id", "isin", name="uix_user_isin"),
        {"schema": "public"},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("public.app_users.user_id", ondelete="CASCADE"),
        index=True,
    )
    isin: Mapped[str] = mapped_column(
        String(12),
        ForeignKey("public.instruments.isin", ondelete="RESTRICT"),
    )
    quantity: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    avg_price: Mapped[Decimal | None] = mapped_column(Numeric(15, 4))
    paper_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )


class Bonds(Base):
    __tablename__ = "bonds"
    __table_args__ = {"schema": "public"}

    isin: Mapped[str] = mapped_column(String(12), primary_key=True)
    extra_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )


class ValorAssetRisk(Base):
    __tablename__ = "valor_asset_risks"
    __table_args__ = (
        UniqueConstraint(
            "asset_type", "identifier", name="uq_valor_asset_type_identifier"
        ),
        CheckConstraint(
            "asset_type IN ('share', 'bond')", name="ck_valor_asset_type"
        ),
        *(
            CheckConstraint(
                f"{column} BETWEEN 1 AND 6",
                name=f"ck_valor_{column}",
            )
            for column in (
                "inflation_risk",
                "geopolitical_risk",
                "domestic_political_risk",
                "debt_risk",
                "currency_risk",
                "minority_shareholder_risk",
            )
        ),
        {"schema": "public"},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    asset_type: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    identifier: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    issuer: Mapped[str] = mapped_column(String(120), nullable=False)
    sector: Mapped[str | None] = mapped_column(String(120))
    company_type: Mapped[str | None] = mapped_column(String(50))
    bond_kind: Mapped[str | None] = mapped_column(String(20))
    currency: Mapped[str | None] = mapped_column(String(10))
    coupon_type: Mapped[str | None] = mapped_column(String(30))
    inflation_risk: Mapped[int | None] = mapped_column(SmallInteger)
    geopolitical_risk: Mapped[int | None] = mapped_column(SmallInteger)
    domestic_political_risk: Mapped[int | None] = mapped_column(SmallInteger)
    debt_risk: Mapped[int | None] = mapped_column(SmallInteger)
    currency_risk: Mapped[int | None] = mapped_column(SmallInteger)
    minority_shareholder_risk: Mapped[int | None] = mapped_column(SmallInteger)
    source_sheet: Mapped[str] = mapped_column(String(50), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


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
