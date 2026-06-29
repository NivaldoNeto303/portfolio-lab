"""Unit tests for app.backtest, using small constructed series."""

from __future__ import annotations

import pandas as pd
import pytest

from app import backtest


def _prices(values: list[float]) -> pd.Series:
    idx = pd.date_range("2023-01-02", periods=len(values), freq="D")
    return pd.Series(values, index=idx, dtype="float64")


def test_ma_crossover_rejects_bad_windows():
    prices = _prices([1, 2, 3, 4, 5])
    with pytest.raises(backtest.BacktestError):
        backtest.ma_crossover(prices, short_window=5, long_window=3)


def test_ma_crossover_no_lookahead_and_alignment():
    # Steadily rising prices: once warmed up the fast MA stays above the slow MA,
    # so the strategy should be invested and match buy-and-hold.
    prices = _prices([float(i) for i in range(1, 21)])
    strat, bh = backtest.ma_crossover(prices, short_window=2, long_window=4)

    assert len(strat) == len(bh)
    assert strat.index.equals(bh.index)
    # While fully invested, strategy return equals the asset return.
    assert strat.iloc[-1] == pytest.approx(bh.iloc[-1])


def test_ma_crossover_goes_to_cash_on_downtrend():
    # Rise then fall: on the way down the strategy should be flat (0 return)
    # on at least some days where buy-and-hold is losing money.
    up = [float(i) for i in range(1, 11)]
    down = [float(i) for i in range(10, 0, -1)]
    strat, bh = backtest.ma_crossover(_prices(up + down), short_window=2, long_window=4)

    # The strategy's worst day is no worse than buy-and-hold's worst day.
    assert strat.min() >= bh.min()
    # And on the final crash day the strategy is in cash (flat).
    assert strat.iloc[-1] == pytest.approx(0.0)


def test_monthly_rebalance_matches_buy_hold_single_asset():
    # With one asset, rebalancing changes nothing: both paths are identical.
    idx = pd.date_range("2023-01-01", periods=70, freq="D")
    prices = pd.Series([100 * (1.01 ** i) for i in range(70)], index=idx)
    strat, bh = backtest.monthly_rebalance({"AAA": prices}, {"AAA": 1.0})
    pd.testing.assert_series_equal(strat, bh)


def test_monthly_rebalance_aligns_and_runs():
    idx = pd.date_range("2023-01-01", periods=70, freq="D")
    a = pd.Series([100 * (1.01 ** i) for i in range(70)], index=idx)
    b = pd.Series([50 * (1.005 ** i) for i in range(70)], index=idx)
    strat, bh = backtest.monthly_rebalance({"A": a, "B": b}, {"A": 0.5, "B": 0.5})

    assert strat.index.equals(bh.index)
    assert len(strat) == 69  # 70 prices -> 69 returns
    # Two assets with different drifts: rebalancing changes the path.
    assert not strat.equals(bh)
