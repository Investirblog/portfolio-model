# ============================================================
# services.py — Logique metier : prix, performance, calculs
# Utilise Financial Modeling Prep (FMP) a la place de yfinance
# ============================================================
import math
import statistics
import httpx
from datetime import date
from typing import List, Optional, Dict
from sqlalchemy.orm import Session
from app.models import Position, PriceCache, PortfolioSnapshot, BenchmarkSnapshot
from app.config import get_settings
import logging

logger = logging.getLogger(__name__)
settings = get_settings()

FMP_BASE = "https://financialmodelingprep.com/api/v3"

FMP_TICKER_MAP = {
    "ESIH.DE": "ESIH.XETRA",
    "ESIS.DE": "ESIS.XETRA",
    "SPYU.DE": "SPYU.XETRA",
    "D5BK.DE": "D5BK.XETRA",
    "SXXP.MI": "SXXP.MI",
}


def _fmp_ticker(ticker: str) -> str:
    return FMP_TICKER_MAP.get(ticker, ticker)


def fetch_price_fmp(ticker: str) -> Optional[float]:
    fmp_t = _fmp_ticker(ticker)
    try:
        url = f"{FMP_BASE}/quote-short/{fmp_t}"
        params = {"apikey": settings.fmp_api_key}
        with httpx.Client(timeout=10) as client:
            resp = client.get(url, params=params)
            data = resp.json()
            if isinstance(data, list) and data:
                price = data[0].get("price")
                if price:
                    return float(price)
            url2 = f"{FMP_BASE}/quote/{fmp_t}"
            resp2 = client.get(url2, params=params)
            data2 = resp2.json()
            if isinstance(data2, list) and data2:
                price2 = data2[0].get("price")
                if price2:
                    return float(price2)
        logger.warning(f"Prix non trouve pour {ticker} ({fmp_t})")
        return None
    except Exception as e:
        logger.error(f"Erreur prix FMP {ticker}: {e}")
        return None


def fetch_prices_fmp_batch(tickers: List[str]) -> Dict[str, float]:
    prices = {}
    us_tickers = [t for t in tickers if "." not in t or t.endswith(".TO")]
    eu_tickers  = [t for t in tickers if "." in t and not t.endswith(".TO")]

    if us_tickers:
        try:
            joined = ",".join(us_tickers)
            url = f"{FMP_BASE}/quote-short/{joined}"
            with httpx.Client(timeout=15) as client:
                resp = client.get(url, params={"apikey": settings.fmp_api_key})
                data = resp.json()
                if isinstance(data, list):
                    for item in data:
                        sym = item.get("symbol", "")
                        price = item.get("price")
                        if sym and price:
                            prices[sym] = float(price)
        except Exception as e:
            logger.error(f"Erreur batch US FMP: {e}")

    for ticker in eu_tickers:
        price = fetch_price_fmp(ticker)
        if price:
            prices[ticker] = price

    return prices


def refresh_prices(db: Session, tickers: List[str]) -> Dict[str, float]:
    prices = fetch_prices_fmp_batch(tickers)
    for ticker, price in prices.items():
        cache = db.query(PriceCache).filter(PriceCache.ticker == ticker).first()
        if cache:
            cache.price = price
            cache.price_date = date.today()
        else:
            db.add(PriceCache(ticker=ticker, price=price, price_date=date.today()))
    db.commit()
    logger.info(f"{len(prices)} prix mis a jour via FMP")
    return prices


def get_cached_price(db: Session, ticker: str) -> Optional[float]:
    cache = db.query(PriceCache).filter(PriceCache.ticker == ticker).first()
    if cache and cache.price:
        return float(cache.price)
    return None


def calculate_portfolio_performance(db: Session) -> dict:
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

    snapshots = db.query(PortfolioSnapshot).order_by(PortfolioSnapshot.snapshot_date).all()

    max_drawdown = 0.0
    volatility_annual = 0.0
    sharpe_ratio = None

    if len(snapshots) >= 2:
        values = [float(s.total_value) for s in snapshots]
        max_drawdown = _calculate_max_drawdown(values)
        volatility_annual = _calculate_volatility(values)
        sharpe_ratio = _calculate_sharpe(values)

    inception_date = snapshots[0].snapshot_date if snapshots else None
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
    if len(values) < 2:
        return 0.0
    returns = [(values[i] - values[i-1]) / values[i-1] for i in range(1, len(values))]
    return float(statistics.stdev(returns) * math.sqrt(trading_days) * 100)


def _calculate_sharpe(values: List[float], risk_free_rate: float = 0.03, trading_days: int = 252) -> Optional[float]:
    if len(values) < 2:
        return None
    returns = [(values[i] - values[i-1]) / values[i-1] for i in range(1, len(values))]
    mean_return = statistics.mean(returns) * trading_days
    vol = statistics.stdev(returns) * math.sqrt(trading_days)
    if vol == 0:
        return None
    return float((mean_return - risk_free_rate) / vol)


def _benchmark_performance(db: Session, inception_date) -> tuple:
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
    today = date.today()
    existing = db.query(PortfolioSnapshot).filter(PortfolioSnapshot.snapshot_date == today).first()
    if existing:
        existing.total_value = total_value
        existing.cash = cash
    else:
        db.add(PortfolioSnapshot(total_value=total_value, cash=cash, snapshot_date=today))
    db.commit()
