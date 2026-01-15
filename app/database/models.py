from sqlalchemy import Column, Integer, String, Identity, BigInteger, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from app.database.session import Base

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

# Определение базы данных для хранения API токенов т-инвестиции пользователей
class User_tokens(Base):
    __tablename__ = "users_t_invest_tokens"
    __table_args__ = {'schema': 'public'}

    user_id = Column(BigInteger, primary_key=True, index=True)
    user_t_invest_token = Column(String, nullable=False)

# Определение базы данных хранения информации об инструментах
class Hash_all_instruments(Base):
    __tablename__ = "hash_all_instruments"
    __table_args__ = {'schema': 'public'}

    isin = Column(String, primary_key=True, index=True)
    inst_data = Column(JSONB, nullable=False)

# Определение базы данных хранения портфеля пользователя
class User_portfolio(Base):
    __tablename__ = "user_portfolio"
    __table_args__ = {"schema": "public"}

    user_id = Column(BigInteger, primary_key=True, index=True)
    portfolio_data = Column(JSONB, nullable=False)