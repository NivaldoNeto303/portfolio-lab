"""Strategy backtester (SPEC.md section 6, Phase 3).

Two simple strategies, each compared against buy-and-hold:

- ``ma_crossover`` (single asset): hold the asset while a short moving average
  is above a long one, otherwise sit in cash. The position is taken on the *next*
  day's open of business (``shift(1)``) so the signal never peeks at the return
  it is used to capture.
- ``monthly_rebalance`` (portfolio): reset to the target weights at the start of
  each month. Buy-and-hold here means the same initial weights left to drift.

Everything returns daily-return Series so the Phase 2 metrics apply unchanged.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


class BacktestError(Exception):
    """Raised on invalid backtest configuration (bad windows, no data)."""


def ma_crossover(
    prices: pd.Series, short_window: int, long_window: int
) -> tuple[pd.Series, pd.Series]:
    """Backtest a moving-average crossover on a single price series.

    Returns ``(strategy_returns, buy_and_hold_returns)`` aligned on the same
    dates (the moving-average warm-up period is dropped from both so the
    comparison is fair).
    """
    if short_window < 1 or long_window < 1:
        raise BacktestError("Moving-average windows must be positive.")
    if short_window >= long_window:
        raise BacktestError("short_window must be smaller than long_window.")

    short_ma = prices.rolling(short_window).mean()
    long_ma = prices.rolling(long_window).mean()

    # Long (1) when the fast MA is above the slow MA, flat/cash (0) otherwise.
    signal = (short_ma > long_ma).astype(float)
    position = signal.shift(1)  # act on the day after the signal forms
    asset_ret = prices.pct_change()

    frame = pd.DataFrame(
        {"position": position, "asset_ret": asset_ret}
    ).dropna()
    if frame.empty:
        raise BacktestError("Not enough price history for the chosen windows.")

    strategy = frame["position"] * frame["asset_ret"]
    buy_hold = frame["asset_ret"]
    return strategy, buy_hold


def _simulate(returns_df: pd.DataFrame, weights: dict[str, float], *, monthly: bool) -> pd.Series:
    """Simulate a portfolio day by day.

    Starting from the target weights (portfolio value 1.0), each asset's slice
    grows by its daily return. When ``monthly`` is true the slices are reset to
    the target weights at the first trading day of each new month; otherwise the
    weights drift (buy-and-hold).
    """
    cols = list(returns_df.columns)
    target = np.array([weights[c] for c in cols], dtype="float64")
    values = target.copy()  # sums to 1.0

    prev_total = 1.0
    current_month: tuple[int, int] | None = None
    out_index, out_returns = [], []

    for ts, row in returns_df.iterrows():
        if monthly:
            month = (ts.year, ts.month)
            if current_month is not None and month != current_month:
                values = target * values.sum()  # rebalance to target
            current_month = month

        values = values * (1.0 + row.to_numpy())
        total = values.sum()
        out_returns.append(total / prev_total - 1.0)
        out_index.append(ts)
        prev_total = total

    return pd.Series(out_returns, index=pd.DatetimeIndex(out_index))


def monthly_rebalance(
    prices_by_ticker: dict[str, pd.Series], weights: dict[str, float]
) -> tuple[pd.Series, pd.Series]:
    """Backtest monthly rebalancing vs. buy-and-hold for a weighted portfolio.

    Returns ``(strategy_returns, buy_and_hold_returns)`` on aligned dates.
    """
    prices = pd.DataFrame(prices_by_ticker).dropna()
    returns_df = prices.pct_change().dropna()
    if returns_df.empty:
        raise BacktestError("Not enough overlapping price history to backtest.")

    total = sum(weights.values())
    norm = {t: w / total for t, w in weights.items()}

    strategy = _simulate(returns_df, norm, monthly=True)
    buy_hold = _simulate(returns_df, norm, monthly=False)
    return strategy, buy_hold
