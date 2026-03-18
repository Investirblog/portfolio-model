# ============================================================
# services.py — Logique métier : prix, performance, calculs
# ============================================================
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import date, timedelta
from typing import List, Optional, Dict
from sqlalchemy.orm import Session
from app.models import Position, PriceCache, PortfolioSnapshot, BenchmarkSnapshot
import logging

logger = logging.getLogger(__name__)

# Tickers des benchmarks
BENCHMARKS = {
    "SPY": "S&P 500",
    "SXXP.MI": "Stoxx 600",   # ETF Stoxx 600 coté Milan
}


# ============================================================
# PRIX
# ============================================================

def fetch_price_yfinance(ticker: str) -> Optional[float]:
    """Récupère le dernier prix d'un ticker via yfinance."""
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="2d")
        if hist.empty:
            logger.warning(f"Pas de données pour {ticker}")
            return None
        return float(hist["Close"].iloc[-1])
    except Exception as e:
        logger.error(f"Erreur prix {ticker}: {e}")
        return None


def refresh_prices(db: Session, tickers: List[str]) -> Dict[str, float]:
    """
    Met à jour le cache de prix pour une liste de tickers.
    Retourne un dict {ticker: price}.
    """
    prices = {}
    for ticker in tickers:
        price = fetch_price_yfinance(ticker)
        if price is not None:
            prices[ticker] = price
            cache = db.query(PriceCache).filter(PriceCache.ticker == ticker).first()
            if cache:
                cache.price = price
                cache.price_date = date.today()
            else:
                db.add(PriceCache(
                    ticker=ticker,
                    price=price,
                    price_date=date.today()
                ))
    db.commit()
    return prices


def get_cached_price(db: Session, ticker: str) -> Optional[float]:
    """Retourne le prix depuis le cache DB."""
    cache = db.query(PriceCache).filter(PriceCache.ticker == ticker).first()
    if cache and cache.price:
        return float(cache.price)
    return None


# ============================================================
# PERFORMANCE
# ============================================================

def calculate_portfolio_performance(db: Session) -> dict:
    """
    Calcule les métriques de performance du portefeuille.
    Retourne un dict compatible avec PerformanceSummary.
    """
    positions = db.query(Position).filter(Position.is_active == True).all()

    if not positions:
        return {
            "total_value": 0, "total_cost": 0, "total_pnl": 0,
            "total_pnl_pct": 0, "max_drawdown": 0, "volatility_annual": 0,
            "sharpe_ratio": None, "inception_date": None,
            "benchmark_spy_pct": None, "benchmark_stoxx_pct": None,
            "portfolio_pct": None
        }

    total_cost = sum(float(p.shares) * float(p.avg_cost) for p in positions)
    total_value = 0.0

    for p in positions:
        price = get_cached_price(db, p.ticker)
        if price:
            total_value += float(p.shares) * price
        else:
            total_value += float(p.shares) * float(p.avg_cost)

    total_pnl = total_value - total_cost
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0

    # Snapshots pour drawdown et volatilité
    snapshots = db.query(PortfolioSnapshot).order_by(
        PortfolioSnapshot.snapshot_date
    ).all()

    max_drawdown = 0.0
    volatility_annual = 0.0
    sharpe_ratio = None

    if len(snapshots) >= 2:
        values = [float(s.total_value) for s in snapshots]
        max_drawdown = _calculate_max_drawdown(values)
        volatility_annual = _calculate_volatility(values)
        sharpe_ratio = _calculate_sharpe(values)

    inception_date = None
    if snapshots:
        inception_date = snapshots[0].snapshot_date

    # Performance benchmarks depuis inception
    spy_pct, stoxx_pct = _benchmark_performance(db, inception_date)

    portfolio_pct = None
    if snapshots:
        first_value = float(snapshots[0].total_value)
        if first_value > 0:
            portfolio_pct = (total_value - first_value) / first_value * 100

    return {
        "total_value": round(total_value, 2),
        "total_cost": round(total_cost, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl_pct, 2),
        "max_drawdown": round(max_drawdown, 2),
        "volatility_annual": round(volatility_annual, 2),
        "sharpe_ratio": round(sharpe_ratio, 2) if sharpe_ratio else None,
        "inception_date": inception_date,
        "benchmark_spy_pct": round(spy_pct, 2) if spy_pct else None,
        "benchmark_stoxx_pct": round(stoxx_pct, 2) if stoxx_pct else None,
        "portfolio_pct": round(portfolio_pct, 2) if portfolio_pct else None,
    }


def _calculate_max_drawdown(values: List[float]) -> float:
    """Calcule le drawdown maximum depuis une série de valeurs."""
    if not values:
        return 0.0
    peak = values[0]
    max_dd = 0.0
    for v in values:
        if v > peak:
            peak = v
        dd = (peak - v) / peak * 100
        if dd > max_dd:
            max_dd = dd
    return max_dd


def _calculate_volatility(values: List[float], trading_days: int = 252) -> float:
    """Volatilité annualisée des rendements quotidiens."""
    if len(values) < 2:
        return 0.0
    returns = [
        (values[i] - values[i-1]) / values[i-1]
        for i in range(1, len(values))
    ]
    return float(np.std(returns) * np.sqrt(trading_days) * 100)


def _calculate_sharpe(
    values: List[float],
    risk_free_rate: float = 0.03,
    trading_days: int = 252
) -> Optional[float]:
    """Ratio de Sharpe simplifié (taux sans risque 3%)."""
    if len(values) < 2:
        return None
    returns = [
        (values[i] - values[i-1]) / values[i-1]
        for i in range(1, len(values))
    ]
    mean_return = np.mean(returns) * trading_days
    vol = np.std(returns) * np.sqrt(trading_days)
    if vol == 0:
        return None
    return float((mean_return - risk_free_rate) / vol)


def _benchmark_performance(
    db: Session,
    inception_date: Optional[date]
) -> tuple:
    """Retourne la performance SPY et Stoxx 600 depuis inception."""
    if not inception_date:
        return None, None

    def _perf(ticker):
        first = db.query(BenchmarkSnapshot).filter(
            BenchmarkSnapshot.benchmark == ticker,
            BenchmarkSnapshot.snapshot_date >= inception_date
        ).order_by(BenchmarkSnapshot.snapshot_date).first()

        last = db.query(BenchmarkSnapshot).filter(
            BenchmarkSnapshot.benchmark == ticker
        ).order_by(BenchmarkSnapshot.snapshot_date.desc()).first()

        if first and last and float(first.price) > 0:
            return (float(last.price) - float(first.price)) / float(first.price) * 100
        return None

    return _perf("SPY"), _perf("SXXP.MI")


def save_daily_snapshot(db: Session, total_value: float, cash: float = 0):
    """Enregistre un snapshot quotidien du portefeuille."""
    today = date.today()
    existing = db.query(PortfolioSnapshot).filter(
        PortfolioSnapshot.snapshot_date == today
    ).first()
    if existing:
        existing.total_value = total_value
        existing.cash = cash
    else:
        db.add(PortfolioSnapshot(
            total_value=total_value,
            cash=cash,
            snapshot_date=today
        ))
    db.commit()
