# ============================================================
# schemas.py — Schémas Pydantic (validation I/O de l'API)
# ============================================================
from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional, Dict, Any
from datetime import date, datetime
from enum import Enum


# --- Enums ---------------------------------------------------

class AssetType(str, Enum):
    stock = "stock"
    etf = "etf"

class TransactionType(str, Enum):
    buy = "buy"
    sell = "sell"
    rebalance = "rebalance"

class Geography(str, Enum):
    US = "US"
    Europe = "Europe"
    Canada = "Canada"


# --- Positions -----------------------------------------------

class PositionCreate(BaseModel):
    ticker: str
    name: str
    asset_type: AssetType
    geography: Geography
    sector: Optional[str] = None
    shares: float
    avg_cost: float
    currency: str = "USD"
    weight_target: Optional[float] = None
    source: Optional[str] = None          # 'screener' | 'macroetf'
    screener_score: Optional[float] = None
    score_details: Optional[Dict[str, Any]] = None
    macro_signal: Optional[str] = None
    rationale: Optional[str] = None       # visible abonnés seulement
    opened_at: date

    @field_validator("ticker")
    @classmethod
    def ticker_upper(cls, v):
        return v.upper().strip()


class PositionPublic(BaseModel):
    """Vue publique — sans raisonnement détaillé."""
    id: int
    ticker: str
    name: str
    asset_type: AssetType
    geography: Geography
    sector: Optional[str]
    shares: float
    avg_cost: float
    currency: str
    weight_target: Optional[float]
    source: Optional[str]
    opened_at: date
    is_public: bool = False
    # Enrichi à la volée par l'API
    current_price: Optional[float] = None
    current_value: Optional[float] = None
    pnl_pct: Optional[float] = None
    weight_actual: Optional[float] = None

    class Config:
        from_attributes = True


class PositionDetail(PositionPublic):
    """Vue abonné — avec raisonnement, scores, signal macro."""
    screener_score: Optional[float]
    score_details: Optional[Dict[str, Any]]
    macro_signal: Optional[str]
    rationale: Optional[str]


# --- Transactions --------------------------------------------

class TransactionCreate(BaseModel):
    ticker: str
    transaction_type: TransactionType
    shares: float
    price: float
    currency: str = "USD"
    rationale: Optional[str] = None
    screener_score: Optional[float] = None
    macro_context: Optional[str] = None
    executed_at: date

    @field_validator("ticker")
    @classmethod
    def ticker_upper(cls, v):
        return v.upper().strip()


class TransactionPublic(BaseModel):
    id: int
    ticker: str
    transaction_type: TransactionType
    shares: float
    price: float
    currency: str
    executed_at: date
    created_at: datetime

    class Config:
        from_attributes = True


class TransactionDetail(TransactionPublic):
    rationale: Optional[str]
    screener_score: Optional[float]
    macro_context: Optional[str]


# --- Performance ---------------------------------------------

class PerformanceSummary(BaseModel):
    """Résumé de performance — vue publique."""
    total_value: float
    total_cost: float
    total_pnl: float
    total_pnl_pct: float
    max_drawdown: float
    volatility_annual: float
    sharpe_ratio: Optional[float]
    inception_date: Optional[date]
    benchmark_spy_pct: Optional[float]    # performance SPY depuis inception
    benchmark_stoxx_pct: Optional[float]  # performance Stoxx 600 depuis inception
    portfolio_pct: Optional[float]        # performance portefeuille depuis inception


# --- Abonnés -------------------------------------------------

class SubscriberCreate(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    source: Optional[str] = "direct"


class SubscriberOut(BaseModel):
    id: int
    email: str
    name: Optional[str]
    subscribed_at: datetime

    class Config:
        from_attributes = True


# --- Auth Admin ----------------------------------------------

class TokenRequest(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
