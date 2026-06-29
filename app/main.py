"""FastAPI application and Phase 1 routes.

Endpoints (SPEC.md section 6, Phase 1):
  POST /assets/{ticker}/sync           fetch from yfinance, upsert into DB
  GET  /assets/{ticker}/prices         return stored series (start/end optional)
  GET  /assets                         list tracked tickers
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlmodel import Session, select

from app import data
from app.db import engine, get_session, init_db
from app.models import Asset, AssetKind, Price


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Portfolio Lab", lifespan=lifespan)


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
