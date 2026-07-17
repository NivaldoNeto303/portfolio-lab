"""Idempotent price persistence, shared by the sync endpoint and the seed loader.

Both write prices the same way: an ``INSERT ... ON CONFLICT(ticker, date) DO
UPDATE`` that overwrites the OHLCV values in place instead of inserting a
duplicate row. Centralizing it here keeps ``main.py`` (live yfinance sync) and
``seed.py`` (offline example load) on a single, tested code path.
"""

from __future__ import annotations

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlmodel import Session, select

from app.models import Asset, AssetKind, Price


def infer_kind(ticker: str) -> AssetKind:
    """Heuristic: B3 FII tickers end in ``11`` (e.g. HGLG11.SA)."""
    base = ticker.upper().removesuffix(".SA")
    return AssetKind.fii if base.endswith("11") else AssetKind.stock


def ensure_asset(session: Session, ticker: str) -> Asset:
    """Return the Asset for ``ticker``, creating it (with an inferred kind) once."""
    asset = session.exec(select(Asset).where(Asset.ticker == ticker)).first()
    if asset is None:
        asset = Asset(ticker=ticker, kind=infer_kind(ticker))
        session.add(asset)
        session.commit()
        session.refresh(asset)
    return asset


# Each row binds 8 columns; SQLite caps bound variables per statement (32766 on
# modern builds), so we insert in chunks to stay well under it. 1000 rows =
# 8000 variables, which is safe and keeps the whole seed to a handful of statements.
_CHUNK_ROWS = 1000


def upsert_prices(session: Session, payload: list[dict]) -> None:
    """Upsert price rows: on a (ticker, date) conflict, overwrite OHLCV in place.

    This is what makes a re-sync (or a re-seed) update existing rows instead of
    duplicating them, honouring the unique constraint on ``Price(ticker, date)``.
    Inserts are chunked so a large payload never exceeds SQLite's variable limit.
    """
    if not payload:
        return
    for start in range(0, len(payload), _CHUNK_ROWS):
        chunk = payload[start : start + _CHUNK_ROWS]
        stmt = sqlite_insert(Price).values(chunk)
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
