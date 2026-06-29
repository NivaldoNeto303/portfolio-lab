"""Historical data fetching.

For now this wraps ``yfinance`` (long OHLCV history). brapi.dev is planned for
quotes/dividends/fundamentals in later phases (see SPEC.md section 3).

We use ``auto_adjust=False`` so the raw ``Close`` and the split/dividend
``Adj Close`` are kept as separate columns: the metrics phase needs adjusted
prices, but storing the raw close too keeps the data faithful to the source.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime

import yfinance as yf

# Brazilian Central Bank SGS API, series 12 = daily CDI rate (% per day).
# Free, no token. Docs: https://dadosabertos.bcb.gov.br/
BCB_SGS_CDI_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados?formato=json"


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


def fetch_cdi(start: date | None = None, end: date | None = None) -> dict[date, float]:
    """Fetch the daily CDI rate from the Brazilian Central Bank (SGS series 12).

    Returns a mapping ``{date: daily_rate}`` where the rate is a decimal per day
    (e.g. 0.00041 for 0.041% a.d.). Used as the risk-free rate for the Sharpe
    ratio. Raises :class:`DataError` on any failure so the caller can fall back
    to rf=0 gracefully.
    """
    url = BCB_SGS_CDI_URL
    if start is not None:
        url += f"&dataInicial={start.strftime('%d/%m/%Y')}"
    if end is not None:
        url += f"&dataFinal={end.strftime('%d/%m/%Y')}"

    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise DataError(f"Failed to fetch CDI from BCB: {exc}") from exc

    if not raw:
        raise DataError("BCB returned no CDI data for the requested range")

    series: dict[date, float] = {}
    for item in raw:
        try:
            day = datetime.strptime(item["data"], "%d/%m/%Y").date()
            # SGS reports the rate as a percent per day; convert to a decimal.
            series[day] = float(item["valor"]) / 100.0
        except (KeyError, ValueError):
            # Skip any malformed record rather than failing the whole fetch.
            continue

    if not series:
        raise DataError("No usable CDI rows returned by BCB")

    return series
