"""Portfolio return/risk metrics (SPEC.md section 6, Phase 2).

Pure functions over pandas Series/DataFrames so the financial math is easy to
unit-test in isolation. Everything is built from *daily simple returns* so the
same code path works for a single asset and for the weighted portfolio.

Conventions:
- Returns are computed from adjusted close (``adj_close``), which already
  incorporates dividends and splits.
- Annualization uses 252 trading days.
- Drawdown and cumulative return are derived from the compounded equity curve.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def daily_returns(prices: pd.Series) -> pd.Series:
    """Daily simple returns from a price series, with the leading NaN dropped."""
    return prices.pct_change().dropna()


def cumulative_return(returns: pd.Series) -> float:
    """Total compounded return over the whole period (e.g. 0.25 = +25%)."""
    if returns.empty:
        return 0.0
    return float((1.0 + returns).prod() - 1.0)


def annualized_return(returns: pd.Series, periods: int = TRADING_DAYS) -> float:
    """Geometric annualized return implied by the period's cumulative return."""
    n = len(returns)
    if n == 0:
        return 0.0
    total = 1.0 + cumulative_return(returns)
    return float(total ** (periods / n) - 1.0)


def annualized_volatility(returns: pd.Series, periods: int = TRADING_DAYS) -> float:
    """Annualized volatility = daily std (sample) scaled by sqrt(periods)."""
    if len(returns) < 2:
        return 0.0
    return float(returns.std(ddof=1) * np.sqrt(periods))


def sharpe_ratio(
    returns: pd.Series,
    risk_free_daily: float | pd.Series = 0.0,
    periods: int = TRADING_DAYS,
) -> float:
    """Annualized Sharpe ratio.

    ``risk_free_daily`` may be a scalar daily rate or a per-date Series (e.g. the
    CDI), which is aligned to ``returns`` before subtracting. Sharpe is the mean
    daily excess return divided by the daily volatility, scaled by sqrt(periods).
    """
    if len(returns) < 2:
        return 0.0
    if isinstance(risk_free_daily, pd.Series):
        rf = risk_free_daily.reindex(returns.index).ffill().fillna(0.0)
    else:
        rf = risk_free_daily
    excess = returns - rf
    vol = returns.std(ddof=1)
    if vol == 0:
        return 0.0
    return float((excess.mean() / vol) * np.sqrt(periods))


def equity_curve(returns: pd.Series) -> pd.Series:
    """Compounded growth of 1 unit invested (e.g. 1.0 -> 1.25 for +25%)."""
    return (1.0 + returns).cumprod()


def drawdown_series(returns: pd.Series) -> pd.Series:
    """Per-date drawdown of the equity curve (0 at peaks, negative below)."""
    equity = equity_curve(returns)
    return equity / equity.cummax() - 1.0


def max_drawdown(returns: pd.Series) -> float:
    """Largest peak-to-trough drop of the equity curve (negative, e.g. -0.30)."""
    if returns.empty:
        return 0.0
    return float(drawdown_series(returns).min())


def returns_frame(prices_by_ticker: dict[str, pd.Series]) -> pd.DataFrame:
    """Align each ticker's prices on shared dates (inner join) and return the
    daily-returns DataFrame. The inner join keeps only days every asset traded,
    which is what correlation and portfolio aggregation require.
    """
    prices = pd.DataFrame(prices_by_ticker).dropna()
    return prices.pct_change().dropna()


def portfolio_returns(returns_df: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    """Weighted daily portfolio returns (fixed weights = daily rebalancing)."""
    w = pd.Series(weights).reindex(returns_df.columns)
    return returns_df.mul(w, axis=1).sum(axis=1)


def correlation_matrix(returns_df: pd.DataFrame) -> pd.DataFrame:
    """Pearson correlation of daily returns across assets."""
    return returns_df.corr()
