"""SQLModel tables for Portfolio Lab.

See SPEC.md section 5 (Data model). The unique constraint on
``Price(ticker, date)`` is what makes syncs idempotent: re-fetching the same
day updates the existing row instead of inserting a duplicate.
"""

from __future__ import annotations

import datetime as dt
from enum import Enum

from sqlmodel import Field, SQLModel, UniqueConstraint


class AssetKind(str, Enum):
    """An asset is either a stock or a real-estate fund (FII)."""

    stock = "stock"
    fii = "fii"


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Asset(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    ticker: str = Field(index=True, unique=True)
    name: str | None = None
    kind: AssetKind = AssetKind.stock
    created_at: dt.datetime = Field(default_factory=_utcnow)


class Price(SQLModel, table=True):
    # One row per (ticker, date); the unique constraint enforces idempotency.
    __table_args__ = (UniqueConstraint("ticker", "date", name="uix_ticker_date"),)

    id: int | None = Field(default=None, primary_key=True)
    ticker: str = Field(index=True)
    date: dt.date = Field(index=True)
    open: float
    high: float
    low: float
    close: float
    adj_close: float
    volume: float
