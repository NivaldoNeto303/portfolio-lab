"""Historical data fetching.

For now this wraps ``yfinance`` (long OHLCV history). brapi.dev is planned for
quotes/dividends/fundamentals in later phases (see SPEC.md section 3).

We use ``auto_adjust=False`` so the raw ``Close`` and the split/dividend
``Adj Close`` are kept as separate columns: the metrics phase needs adjusted
prices, but storing the raw close too keeps the data faithful to the source.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import yfinance as yf


class DataError(Exception):
    """Raised when data cannot be fetched (unknown ticker, network, empty)."""


@dataclass(frozen=True)
class PriceRow:
    date: date
    open: float
    high: float
    low: float
    close: float
    adj_close: float
    volume: float


# yfinance column name -> PriceRow field name.
_COLUMN_MAP = {
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Adj Close": "adj_close",
    "Volume": "volume",
}


def fetch_history(ticker: str, start: str | None = None) -> list[PriceRow]:
    """Fetch daily OHLCV history for ``ticker`` from yfinance.

    ``start`` is an optional ISO date (``YYYY-MM-DD``); when omitted yfinance
    returns the maximum available history. Raises :class:`DataError` for
    network failures, unknown tickers, or empty responses so callers never see
    a bare crash.
    """
    try:
        frame = yf.download(
            ticker,
            start=start,
            auto_adjust=False,
            progress=False,
            # One ticker at a time keeps the returned columns flat and simple.
            group_by="column",
        )
    except Exception as exc:  # yfinance surfaces network errors as plain Exceptions
        raise DataError(f"Failed to fetch history for {ticker!r}: {exc}") from exc

    if frame is None or frame.empty:
        raise DataError(f"No price data returned for {ticker!r} (unknown ticker?)")

    # With a single ticker yfinance may still return a MultiIndex on columns;
    # flatten it so we can address columns by their plain name.
    if hasattr(frame.columns, "nlevels") and frame.columns.nlevels > 1:
        frame = frame.droplevel(axis=1, level=-1)

    missing = [col for col in _COLUMN_MAP if col not in frame.columns]
    if missing:
        raise DataError(
            f"Unexpected data shape for {ticker!r}; missing columns: {missing}"
        )

    rows: list[PriceRow] = []
    for index, record in frame.iterrows():
        # Skip rows with no close (occasional yfinance NaN gaps).
        if record["Close"] != record["Close"]:  # NaN check without importing math
            continue
        rows.append(
            PriceRow(
                date=index.date(),
                open=float(record["Open"]),
                high=float(record["High"]),
                low=float(record["Low"]),
                close=float(record["Close"]),
                adj_close=float(record["Adj Close"]),
                volume=float(record["Volume"]),
            )
        )

    if not rows:
        raise DataError(f"No usable price rows for {ticker!r}")

    return rows
