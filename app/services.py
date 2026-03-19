# ============================================================
# services.py — Prix via Twelve Data, performance, calculs
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

TD_BASE = "https://api.twelvedata.com"

# Correspondance tickers locaux -> tickers Twelve Data
TD_TICKER_MAP = {
    "ESIH.DE": "ESIH",
    "ESIS.DE": "ESIS",
    "SPYU.DE": "SPYU",
    "D5BK.DE": "D5BK",
}

TD_EXCHANGE_MAP = {
    "ESIH.DE": "XETRA",
    "ESIS.DE": "XETRA",
    "SPYU.DE": "XETRA",
    "D5BK.DE": "XETRA",
    "SXXP.MI": "MIL",
    "B":       "NYSE",
}


def fetch_prices_batch(tickers: List[str]) -> Dict[str, float]:
    """
    Recupere les prix en batch via Twelve Data.
    Max ~8 tickers par requete sur le plan gratuit.
    """
    prices = {}

    def _td_symbol(ticker):
        return TD_TICKER_MAP.get(ticker, ticker)

    def _td_exchange(ticker):
        return TD_EXCHANGE_MAP.get(ticker)

    # Separer US/Canada et Europe
    us_tickers = [t for t in tickers if t not in TD_TICKER_MAP and t != "SXXP.MI"]
    eu_tickers  = [t for t in tickers if t in TD_TICKER_MAP or t == "SXXP.MI"]

    # Batch US (symboles simples)
    if us_tickers:
        try:
            symbols = ",".join(us_tickers)
            url = f"{TD_BASE}/price"
            params = {"symbol": symbols, "apikey": settings.fmp_api_key}
            with httpx.Client(timeout=15) as client:
                resp = client.get(url, params=params)
                data = resp.json()
                # Reponse batch : dict {TICKER: {price: ...}} ou direct si 1 ticker
                if isinstance(data, dict):
                    if "price" in data:
                        # 1 seul ticker retourne direct
                        if len(us_tickers) == 1:
                            prices[us_tickers[0]] = float(data["price"])
                    else:
                        for ticker in us_tickers:
                            item = data.get(ticker, {})
                            if isinstance(item, dict) and "price" in item:
                                prices[ticker] = float(item["price"])
        except Exception as e:
            logger.error(f"Erreur batch Twelve Data US: {e}")

    # ETF europeens — requetes individuelles avec exchange
    for ticker in eu_tickers:
        try:
            symbol = _td_symbol(ticker)
            exchange = _td_exchange(ticker)
            params = {"symbol": symbol, "apikey": settings.fmp_api_key}
            if exchange:
                params["exchange"] = exchange
            url = f"{TD_BASE}/price"
            with httpx.Client(timeout=10) as client:
                resp = client.get(url, params=params)
                data = resp.json()
                if isinstance(data, dict) and "price" in data:
                    prices[ticker] = float(data["price"])
                else:
                    logger.warning(f"Prix non trouve pour {ticker}: {data}")
        except Exception as e:
            logger.error(f"Erreur Twelve Data {ticker}: {e}")

    return prices


def refresh_prices(db: Session, tickers: List[str]) -> Dict[str, float]:
    prices = fetch_prices_batch(tickers)
    for ticker, price in prices.items():
        cache = db.query(PriceCache).filter(PriceCache.ticker == ticker).first()
        if cache:
            cache.price = price
            cache.price_date = date.today()
        else:
            db.add(PriceCache(ticker=ticker, price=price, price_date=date.today()))
    db.commit()
    logger.info(f"{len(prices)} prix mis a jour via Twelve Data")
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


def _calculate_max_drawdown(values):
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


def _calculate_volatility(values, trading_days=252):
    if len(values) < 2:
        return 0.0
    returns = [(values[i] - values[i-1]) / values[i-1] for i in range(1, len(values))]
    return float(statistics.stdev(returns) * math.sqrt(trading_days) * 100)


def _calculate_sharpe(values, risk_free_rate=0.03, trading_days=252):
    if len(values) < 2:
        return None
    returns = [(values[i] - values[i-1]) / values[i-1] for i in range(1, len(values))]
    mean_return = statistics.mean(returns) * trading_days
    vol = statistics.stdev(returns) * math.sqrt(trading_days)
    if vol == 0:
        return None
    return float((mean_return - risk_free_rate) / vol)


def _benchmark_performance(db, inception_date):
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


def save_daily_snapshot(db, total_value, cash=0):
    today = date.today()
    existing = db.query(PortfolioSnapshot).filter(
        PortfolioSnapshot.snapshot_date == today
    ).first()
    if existing:
        existing.total_value = total_value
        existing.cash = cash
    else:
        db.add(PortfolioSnapshot(total_value=total_value, cash=cash, snapshot_date=today))
    db.commit()
