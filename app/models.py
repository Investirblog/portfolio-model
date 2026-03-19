# ============================================================
# models.py — Modèles SQLAlchemy (miroir du schéma SQL)
# ============================================================
from sqlalchemy import (
    Column, Integer, String, Numeric, Boolean, Date, Text,
    DateTime, Enum, ForeignKey, JSON
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func
import enum

Base = declarative_base()


class AssetTypeEnum(str, enum.Enum):
    stock = "stock"
    etf = "etf"


class TransactionTypeEnum(str, enum.Enum):
    buy = "buy"
    sell = "sell"
    rebalance = "rebalance"


class GeographyEnum(str, enum.Enum):
    US = "US"
    Europe = "Europe"
    Canada = "Canada"


class Position(Base):
    __tablename__ = "positions"

    id              = Column(Integer, primary_key=True)
    ticker          = Column(String(20), nullable=False, unique=True)
    name            = Column(String(200), nullable=False)
    asset_type      = Column(Enum(AssetTypeEnum), nullable=False)
    geography       = Column(Enum(GeographyEnum), nullable=False)
    sector          = Column(String(100))
    shares          = Column(Numeric(12, 4), nullable=False)
    avg_cost        = Column(Numeric(12, 4), nullable=False)
    currency        = Column(String(3), default="USD")
    weight_target   = Column(Numeric(5, 2))
    source          = Column(String(50))           # 'screener' | 'macroetf' | 'manual'
    screener_score  = Column(Numeric(5, 2))
    score_details   = Column(JSON)
    macro_signal    = Column(String(200))
    rationale       = Column(Text)
    opened_at       = Column(Date, nullable=False)
    is_active       = Column(Boolean, default=True)
    is_public       = Column(Boolean, default=False)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), onupdate=func.now())


class Transaction(Base):
    __tablename__ = "transactions"

    id               = Column(Integer, primary_key=True)
    ticker           = Column(String(20), nullable=False)
    transaction_type = Column(Enum(TransactionTypeEnum), nullable=False)
    shares           = Column(Numeric(12, 4), nullable=False)
    price            = Column(Numeric(12, 4), nullable=False)
    currency         = Column(String(3), default="USD")
    rationale        = Column(Text)
    screener_score   = Column(Numeric(5, 2))
    macro_context    = Column(String(200))
    executed_at      = Column(Date, nullable=False)
    created_at       = Column(DateTime(timezone=True), server_default=func.now())


class PriceCache(Base):
    __tablename__ = "price_cache"

    ticker      = Column(String(20), primary_key=True)
    price       = Column(Numeric(12, 4))
    currency    = Column(String(3), default="USD")
    price_date  = Column(Date)
    fetched_at  = Column(DateTime(timezone=True), server_default=func.now())


class BenchmarkSnapshot(Base):
    __tablename__ = "benchmark_snapshots"

    id            = Column(Integer, primary_key=True)
    benchmark     = Column(String(20), nullable=False)   # 'SPY', 'SXXP'
    price         = Column(Numeric(12, 4), nullable=False)
    snapshot_date = Column(Date, nullable=False)


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id            = Column(Integer, primary_key=True)
    total_value   = Column(Numeric(14, 2), nullable=False)
    cash          = Column(Numeric(14, 2), default=0)
    snapshot_date = Column(Date, nullable=False, unique=True)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())


class Subscriber(Base):
    __tablename__ = "subscribers"

    id              = Column(Integer, primary_key=True)
    email           = Column(String(255), nullable=False, unique=True)
    name            = Column(String(100))
    is_active       = Column(Boolean, default=True)
    is_public       = Column(Boolean, default=False)
    subscribed_at   = Column(DateTime(timezone=True), server_default=func.now())
    unsubscribed_at = Column(DateTime(timezone=True))
    source          = Column(String(50))


class EmailLog(Base):
    __tablename__ = "email_logs"

    id               = Column(Integer, primary_key=True)
    transaction_id   = Column(Integer, ForeignKey("transactions.id"))
    subject          = Column(String(300))
    recipients_count = Column(Integer)
    sent_at          = Column(DateTime(timezone=True), server_default=func.now())
    status           = Column(String(50))


class AdminUser(Base):
    __tablename__ = "admin_user"

    id              = Column(Integer, primary_key=True)
    username        = Column(String(50), nullable=False, unique=True)
    hashed_password = Column(String(255), nullable=False)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
