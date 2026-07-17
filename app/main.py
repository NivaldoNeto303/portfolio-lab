"""FastAPI application and Phase 1 routes.

Endpoints (SPEC.md section 6, Phase 1):
  POST /assets/{ticker}/sync           fetch from yfinance, upsert into DB
  GET  /assets/{ticker}/prices         return stored series (start/end optional)
  GET  /assets                         list tracked tickers
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Literal

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlmodel import Session, select

from app import backtest, data, metrics, tickers
from app.db import engine, get_session, init_db
from app.models import Asset, AssetKind, Price

DASHBOARD_HTML = Path(__file__).parent / "templates" / "dashboard.html"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Portfolio Lab", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
def dashboard():
    """Serve the single-page Chart.js dashboard (Phase 4)."""
    return FileResponse(DASHBOARD_HTML)


@app.get("/tickers")
def search_tickers(
    q: str = Query("", description="Case-insensitive ticker substring"),
    limit: int = Query(15, ge=1, le=50),
) -> dict:
    """Autocomplete source for the ticker search box (Phase 5).

    Filters the B3 universe (cached from brapi.dev, curated fallback offline).
    Returns bare codes; the client appends the ``.SA`` Yahoo suffix.
    """
    return tickers.search(q, limit)


def _infer_kind(ticker: str) -> AssetKind:
    """Heuristic: B3 FII tickers end in ``11`` (e.g. HGLG11.SA)."""
    base = ticker.upper().removesuffix(".SA")
    return AssetKind.fii if base.endswith("11") else AssetKind.stock


def _ensure_asset(session: Session, ticker: str) -> Asset:
    asset = session.exec(select(Asset).where(Asset.ticker == ticker)).first()
    if asset is None:
        asset = Asset(ticker=ticker, kind=_infer_kind(ticker))
        session.add(asset)
        session.commit()
        session.refresh(asset)
    return asset


@app.post("/assets/{ticker}/sync")
def sync_asset(
    ticker: str,
    start: str | None = Query(default=None, description="ISO start date, YYYY-MM-DD"),
    session: Session = Depends(get_session),
) -> dict:
    """Fetch history from yfinance and upsert it. Safe to re-run (idempotent)."""
    ticker = ticker.upper()
    try:
        rows = data.fetch_history(ticker, start=start)
    except data.DataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    _ensure_asset(session, ticker)

    # Upsert: on a (ticker, date) conflict, overwrite the OHLCV values. This is
    # what makes a re-sync update rows in place instead of duplicating them.
    payload = [
        {
            "ticker": ticker,
            "date": r.date,
            "open": r.open,
            "high": r.high,
            "low": r.low,
            "close": r.close,
            "adj_close": r.adj_close,
            "volume": r.volume,
        }
        for r in rows
    ]
    stmt = sqlite_insert(Price).values(payload)
    stmt = stmt.on_conflict_do_update(
        index_elements=["ticker", "date"],
        set_={
            "open": stmt.excluded.open,
            "high": stmt.excluded.high,
            "low": stmt.excluded.low,
            "close": stmt.excluded.close,
            "adj_close": stmt.excluded.adj_close,
            "volume": stmt.excluded.volume,
        },
    )
    session.exec(stmt)
    session.commit()

    return {
        "ticker": ticker,
        "rows_synced": len(rows),
        "start": rows[0].date.isoformat(),
        "end": rows[-1].date.isoformat(),
    }


@app.get("/assets/{ticker}/prices")
def get_prices(
    ticker: str,
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    session: Session = Depends(get_session),
) -> list[Price]:
    """Return the stored price series for a ticker, optionally date-bounded."""
    ticker = ticker.upper()
    query = select(Price).where(Price.ticker == ticker)
    if start is not None:
        query = query.where(Price.date >= start)
    if end is not None:
        query = query.where(Price.date <= end)
    query = query.order_by(Price.date)

    prices = session.exec(query).all()
    if not prices:
        raise HTTPException(
            status_code=404,
            detail=f"No stored prices for {ticker!r}; sync it first.",
        )
    return prices


@app.get("/assets")
def list_assets(session: Session = Depends(get_session)) -> list[Asset]:
    """List tracked assets."""
    return session.exec(select(Asset).order_by(Asset.ticker)).all()


# --------------------------------------------------------------------------- #
# Phase 2 — Portfolio metrics
# --------------------------------------------------------------------------- #


class Holding(BaseModel):
    ticker: str
    weight: float = Field(gt=0, description="Relative weight; normalized to sum to 1.")


class AnalyzeRequest(BaseModel):
    holdings: list[Holding] = Field(min_length=1)
    start: date | None = None
    end: date | None = None
    # If omitted, the CDI is fetched from BCB and used as the risk-free rate.
    risk_free_annual: float | None = None


def _load_adj_close(
    session: Session, ticker: str, start: date | None, end: date | None
) -> pd.Series:
    """Load the stored adjusted-close series for a ticker as a date-indexed Series."""
    query = select(Price).where(Price.ticker == ticker)
    if start is not None:
        query = query.where(Price.date >= start)
    if end is not None:
        query = query.where(Price.date <= end)
    rows = session.exec(query.order_by(Price.date)).all()
    return pd.Series(
        {pd.Timestamp(r.date): r.adj_close for r in rows}, dtype="float64"
    )


def _risk_free_daily(
    risk_free_annual: float | None, index: pd.DatetimeIndex
) -> tuple[float | pd.Series, str]:
    """Resolve the daily risk-free rate and a human-readable note about its source."""
    if risk_free_annual is not None:
        daily = (1.0 + risk_free_annual) ** (1.0 / metrics.TRADING_DAYS) - 1.0
        return daily, f"manual risk_free_annual={risk_free_annual}"

    # Default: fetch the CDI; fall back to rf=0 if BCB is unreachable.
    start = index.min().date()
    end = index.max().date()
    try:
        cdi = data.fetch_cdi(start=start, end=end)
    except data.DataError as exc:
        return 0.0, f"CDI unavailable ({exc}); used rf=0"
    rf = pd.Series({pd.Timestamp(d): v for d, v in cdi.items()}, dtype="float64")
    return rf, "CDI (BCB SGS series 12)"


def _metrics_block(returns: pd.Series, rf_daily: float | pd.Series) -> dict:
    """The standard set of return/risk metrics for one return series."""
    return {
        "cumulative_return": metrics.cumulative_return(returns),
        "annualized_return": metrics.annualized_return(returns),
        "annualized_volatility": metrics.annualized_volatility(returns),
        "sharpe_ratio": metrics.sharpe_ratio(returns, rf_daily),
        "max_drawdown": metrics.max_drawdown(returns),
    }


def _annualized_rf(rf_daily: float | pd.Series) -> float:
    """Annualize the daily risk-free rate for display (does not affect any metric).

    Purely presentational: surfaces the CDI as an annual percentage so the
    dashboard can contextualize returns against it.
    """
    if isinstance(rf_daily, pd.Series):
        daily = float(rf_daily.mean()) if not rf_daily.empty else 0.0
    else:
        daily = float(rf_daily)
    return (1.0 + daily) ** metrics.TRADING_DAYS - 1.0


@app.post("/portfolio/analyze")
def analyze_portfolio(
    req: AnalyzeRequest, session: Session = Depends(get_session)
) -> dict:
    """Compute return/risk metrics for a weighted portfolio from stored prices."""
    tickers = [h.ticker.upper() for h in req.holdings]

    prices: dict[str, pd.Series] = {}
    missing: list[str] = []
    for ticker in tickers:
        series = _load_adj_close(session, ticker, req.start, req.end)
        if series.empty:
            missing.append(ticker)
        else:
            prices[ticker] = series
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"No stored prices for {missing}; sync these tickers first.",
        )

    # Normalize weights to sum to 1 (note it if the input didn't already).
    raw_weights = {h.ticker.upper(): h.weight for h in req.holdings}
    total = sum(raw_weights.values())
    weights = {t: w / total for t, w in raw_weights.items()}
    normalized = abs(total - 1.0) > 1e-9

    returns_df = metrics.returns_frame(prices)
    if returns_df.empty:
        raise HTTPException(
            status_code=400,
            detail="Not enough overlapping price history to compute returns.",
        )

    rf_daily, rf_note = _risk_free_daily(req.risk_free_annual, returns_df.index)
    port_ret = metrics.portfolio_returns(returns_df, weights)

    per_asset = {
        ticker: _metrics_block(returns_df[ticker], rf_daily)
        for ticker in returns_df.columns
    }
    corr = metrics.correlation_matrix(returns_df)

    return {
        "weights": weights,
        "weights_normalized": normalized,
        "period": {
            "start": returns_df.index.min().date().isoformat(),
            "end": returns_df.index.max().date().isoformat(),
            "trading_days": int(len(returns_df)),
        },
        "risk_free": rf_note,
        "risk_free_annual": _annualized_rf(rf_daily),
        "portfolio": _metrics_block(port_ret, rf_daily),
        "assets": per_asset,
        "correlation": {
            col: corr[col].round(4).to_dict() for col in corr.columns
        },
    }


# --------------------------------------------------------------------------- #
# Phase 3 — Backtester
# --------------------------------------------------------------------------- #


class BacktestRequest(BaseModel):
    strategy: Literal["ma_crossover", "monthly_rebalance"]
    start: date | None = None
    end: date | None = None
    risk_free_annual: float | None = None
    # ma_crossover params
    ticker: str | None = None
    short_window: int = 20
    long_window: int = 50
    # monthly_rebalance params
    holdings: list[Holding] | None = None


def _equity_payload(returns: pd.Series) -> list[float]:
    """Equity curve as a plain list, rounded for a compact JSON response."""
    return [round(v, 6) for v in metrics.equity_curve(returns)]


def _backtest_result(
    strategy_ret: pd.Series,
    buy_hold_ret: pd.Series,
    rf_annual: float | None,
) -> dict:
    """Assemble the comparison payload (metrics + curves) for the dashboard."""
    rf_daily, rf_note = _risk_free_daily(rf_annual, strategy_ret.index)
    dates = [ts.date().isoformat() for ts in strategy_ret.index]
    return {
        "risk_free": rf_note,
        "risk_free_annual": _annualized_rf(rf_daily),
        "dates": dates,
        "strategy": {
            "metrics": _metrics_block(strategy_ret, rf_daily),
            "equity": _equity_payload(strategy_ret),
            "drawdown": [round(v, 6) for v in metrics.drawdown_series(strategy_ret)],
        },
        "buy_and_hold": {
            "metrics": _metrics_block(buy_hold_ret, rf_daily),
            "equity": _equity_payload(buy_hold_ret),
            "drawdown": [round(v, 6) for v in metrics.drawdown_series(buy_hold_ret)],
        },
    }


@app.post("/backtest")
def run_backtest(
    req: BacktestRequest, session: Session = Depends(get_session)
) -> dict:
    """Backtest a strategy against buy-and-hold over stored prices."""
    if req.strategy == "ma_crossover":
        if not req.ticker:
            raise HTTPException(400, "ma_crossover requires a 'ticker'.")
        ticker = req.ticker.upper()
        prices = _load_adj_close(session, ticker, req.start, req.end)
        if prices.empty:
            raise HTTPException(400, f"No stored prices for {ticker!r}; sync it first.")
        try:
            strat, bh = backtest.ma_crossover(prices, req.short_window, req.long_window)
        except backtest.BacktestError as exc:
            raise HTTPException(400, str(exc)) from exc
        meta = {
            "ticker": ticker,
            "short_window": req.short_window,
            "long_window": req.long_window,
        }
    else:  # monthly_rebalance
        if not req.holdings:
            raise HTTPException(400, "monthly_rebalance requires 'holdings'.")
        prices_by_ticker: dict[str, pd.Series] = {}
        missing: list[str] = []
        for h in req.holdings:
            t = h.ticker.upper()
            series = _load_adj_close(session, t, req.start, req.end)
            if series.empty:
                missing.append(t)
            else:
                prices_by_ticker[t] = series
        if missing:
            raise HTTPException(400, f"No stored prices for {missing}; sync them first.")
        weights = {h.ticker.upper(): h.weight for h in req.holdings}
        try:
            strat, bh = backtest.monthly_rebalance(prices_by_ticker, weights)
        except backtest.BacktestError as exc:
            raise HTTPException(400, str(exc)) from exc
        total = sum(weights.values())
        meta = {"weights": {t: w / total for t, w in weights.items()}}

    result = _backtest_result(strat, bh, req.risk_free_annual)
    return {"strategy_name": req.strategy, **meta, **result}
