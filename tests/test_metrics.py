"""Unit tests for app.metrics, using small hand-checked series."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app import metrics


def test_cumulative_return():
    r = pd.Series([0.02, 0.01, 0.03])
    # 1.02 * 1.01 * 1.03 - 1
    assert metrics.cumulative_return(r) == pytest.approx(0.061106)


def test_cumulative_return_empty():
    assert metrics.cumulative_return(pd.Series([], dtype="float64")) == 0.0


def test_annualized_volatility():
    r = pd.Series([0.01, -0.01])
    # std(ddof=1) = sqrt(0.0002) = 0.0141421; * sqrt(252)
    expected = np.sqrt(0.0002) * np.sqrt(252)
    assert metrics.annualized_volatility(r) == pytest.approx(expected)


def test_volatility_too_short_is_zero():
    assert metrics.annualized_volatility(pd.Series([0.01])) == 0.0


def test_sharpe_ratio_rf_zero():
    r = pd.Series([0.02, 0.01, 0.03])
    # mean=0.02, std(ddof=1)=0.01 -> (0.02/0.01)*sqrt(252)
    expected = 2.0 * np.sqrt(252)
    assert metrics.sharpe_ratio(r, 0.0) == pytest.approx(expected)


def test_sharpe_ratio_with_risk_free_reduces():
    r = pd.Series([0.02, 0.01, 0.03])
    assert metrics.sharpe_ratio(r, 0.005) < metrics.sharpe_ratio(r, 0.0)


def test_max_drawdown():
    # equity: 1.1, 0.55, 0.66 -> worst dd = 0.55/1.1 - 1 = -0.5
    r = pd.Series([0.1, -0.5, 0.2])
    assert metrics.max_drawdown(r) == pytest.approx(-0.5)


def test_max_drawdown_monotonic_up_is_zero():
    r = pd.Series([0.1, 0.1, 0.1])
    assert metrics.max_drawdown(r) == pytest.approx(0.0)


def test_returns_frame_inner_join():
    a = pd.Series(
        [10.0, 11.0, 12.0],
        index=pd.to_datetime(["2023-01-02", "2023-01-03", "2023-01-04"]),
    )
    # b is missing 2023-01-04 -> that day is dropped from the aligned frame.
    b = pd.Series(
        [20.0, 22.0], index=pd.to_datetime(["2023-01-02", "2023-01-03"])
    )
    frame = metrics.returns_frame({"A": a, "B": b})
    assert list(frame.columns) == ["A", "B"]
    # 2 aligned prices -> 1 return row
    assert len(frame) == 1


def test_portfolio_returns_weighted_sum():
    df = pd.DataFrame({"A": [0.10, 0.10], "B": [0.00, 0.00]})
    out = metrics.portfolio_returns(df, {"A": 0.5, "B": 0.5})
    assert out.tolist() == pytest.approx([0.05, 0.05])


def test_correlation_perfectly_correlated():
    df = pd.DataFrame({"A": [0.01, 0.02, 0.03], "B": [0.02, 0.04, 0.06]})
    corr = metrics.correlation_matrix(df)
    assert corr.loc["A", "B"] == pytest.approx(1.0)
