"""Backend validation for the two recent features.

(A) The dashboard auto-loads an example portfolio (PETR4.SA 0.4, VALE3.SA 0.3,
    HGLG11.SA 0.3) and runs analyze + monthly-rebalance backtest on load.
(B) The drawdown chart shows a percentage axis / formatted tooltips (frontend
    only — here we just assert the served page wires it up).

These complement the existing suite: they exercise the *example portfolio*
end-to-end through /portfolio/analyze and /backtest, assert the full metric
structure, and confirm the served dashboard contains the auto-load wiring.
Prices are seeded directly (yfinance untouched) and the CDI is mocked, matching
tests/test_portfolio.py and tests/test_backtest_api.py.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import pytest

from app import data, main
from app.models import Price
from sqlmodel import select

# The example portfolio the dashboard boots with (see DEFAULT_PORTFOLIO in
# dashboard.html). HGLG11 ends in "11" so it is inferred as a FII.
EXAMPLE_HOLDINGS = [
    {"ticker": "PETR4.SA", "weight": 0.4},
    {"ticker": "VALE3.SA", "weight": 0.3},
    {"ticker": "HGLG11.SA", "weight": 0.3},
]

METRIC_KEYS = {
    "cumulative_return",
    "annualized_return",
    "annualized_volatility",
    "sharpe_ratio",
    "max_drawdown",
}


def _wavy(base: float, amp: float, drift: float, phase: float, n: int = 90) -> list[float]:
    """A rising series with an oscillation, so drawdowns/vol/correlation are
    non-degenerate but fully deterministic."""
    return [round(base + drift * i + amp * math.sin(i / 6.0 + phase), 4) for i in range(n)]


def _seed_prices(session, ticker: str, closes: list[float]) -> None:
    start = date(2023, 1, 2)
    for i, c in enumerate(closes):
        session.add(
            Price(
                ticker=ticker,
                date=start + timedelta(days=i),
                open=c, high=c, low=c, close=c, adj_close=c, volume=1000.0,
            )
        )
    session.commit()


def _seed_example(session) -> None:
    # Different phases/amplitudes → imperfect correlation between the three.
    _seed_prices(session, "PETR4.SA", _wavy(30, 3.0, 0.15, phase=0.0))
    _seed_prices(session, "VALE3.SA", _wavy(60, 4.0, 0.05, phase=1.3))
    _seed_prices(session, "HGLG11.SA", _wavy(100, 2.0, 0.08, phase=2.6))


@pytest.fixture(autouse=True)
def _no_network_cdi(monkeypatch):
    """CDI offline by default (rf falls back cleanly), like the sibling tests."""
    def boom(*a, **k):
        raise main.data.DataError("offline in tests")

    monkeypatch.setattr(main.data, "fetch_cdi", boom)


# --------------------------------------------------------------------------- #
# Feature A — /portfolio/analyze with the example portfolio
# --------------------------------------------------------------------------- #
def test_analyze_example_portfolio_structure(client, session):
    _seed_example(session)
    resp = client.post(
        "/portfolio/analyze",
        json={"holdings": EXAMPLE_HOLDINGS, "risk_free_annual": 0.0},
    )
    assert resp.status_code == 200
    body = resp.json()

    # Weights are the example allocation (0.4/0.3/0.3 already sums to 1).
    assert body["weights"]["PETR4.SA"] == pytest.approx(0.4)
    assert body["weights"]["VALE3.SA"] == pytest.approx(0.3)
    assert body["weights"]["HGLG11.SA"] == pytest.approx(0.3)
    assert body["weights_normalized"] is False

    # Period block.
    assert body["period"]["trading_days"] > 0

    # Portfolio + per-asset metric blocks: all five keys, all floats.
    assert METRIC_KEYS <= set(body["portfolio"])
    for m in body["portfolio"].values():
        assert isinstance(m, float)
    assert set(body["assets"]) == {"PETR4.SA", "VALE3.SA", "HGLG11.SA"}
    for asset in body["assets"].values():
        assert METRIC_KEYS <= set(asset)
        assert all(isinstance(v, float) for v in asset.values())

    # Volatility is non-negative; a wavy series has a real (negative) drawdown.
    assert body["portfolio"]["annualized_volatility"] >= 0
    assert body["portfolio"]["max_drawdown"] <= 0

    # Correlation: 3x3 with a unit diagonal and values within [-1, 1].
    corr = body["correlation"]
    assert set(corr) == {"PETR4.SA", "VALE3.SA", "HGLG11.SA"}
    for t in corr:
        assert corr[t][t] == pytest.approx(1.0)
        for v in corr[t].values():
            assert -1.0 <= v <= 1.0


# --------------------------------------------------------------------------- #
# Feature A — /backtest monthly_rebalance with the example portfolio
# --------------------------------------------------------------------------- #
def test_backtest_example_monthly_rebalance(client, session):
    _seed_example(session)
    resp = client.post(
        "/backtest",
        json={
            "strategy": "monthly_rebalance",
            "holdings": EXAMPLE_HOLDINGS,
            "risk_free_annual": 0.0,
        },
    )
    assert resp.status_code == 200
    body = resp.json()

    assert body["strategy_name"] == "monthly_rebalance"
    assert body["weights"]["PETR4.SA"] == pytest.approx(0.4)

    n = len(body["dates"])
    assert n > 0
    # Both series present, aligned to the dates, for strategy and buy & hold.
    for side in ("strategy", "buy_and_hold"):
        assert METRIC_KEYS <= set(body[side]["metrics"])
        assert len(body[side]["equity"]) == n
        assert len(body[side]["drawdown"]) == n
        # Drawdown is a fraction <= 0 (feeds the "%" axis on the frontend).
        assert all(d <= 1e-9 for d in body[side]["drawdown"])


# --------------------------------------------------------------------------- #
# Sync idempotency — re-syncing must not duplicate rows, and upserts in place
# --------------------------------------------------------------------------- #
def test_sync_example_ticker_idempotent_and_upserts(client, session, monkeypatch):
    first = [data.PriceRow(date(2023, 1, 2), 10.0, 10.5, 9.5, 10.2, 10.0, 1000.0)]
    monkeypatch.setattr(main.data, "fetch_history", lambda ticker, start=None: first)

    client.post("/assets/PETR4.SA/sync")
    client.post("/assets/PETR4.SA/sync")  # same day again → no duplicate

    rows = session.exec(select(Price).where(Price.ticker == "PETR4.SA")).all()
    assert len(rows) == 1  # unique (ticker, date) respected

    # A re-sync with new values for the same date overwrites in place (upsert).
    updated = [data.PriceRow(date(2023, 1, 2), 10.0, 10.5, 9.5, 99.9, 99.0, 1000.0)]
    monkeypatch.setattr(main.data, "fetch_history", lambda ticker, start=None: updated)
    client.post("/assets/PETR4.SA/sync")

    rows = session.exec(select(Price).where(Price.ticker == "PETR4.SA")).all()
    assert len(rows) == 1
    assert rows[0].close == 99.9  # value was updated, not duplicated


# --------------------------------------------------------------------------- #
# CDI unavailable → rf falls back to 0 and the response says so
# --------------------------------------------------------------------------- #
def test_analyze_cdi_unavailable_falls_back_to_zero(client, session):
    _seed_example(session)
    # No risk_free_annual → tries CDI, which the autouse fixture makes fail.
    resp = client.post("/portfolio/analyze", json={"holdings": EXAMPLE_HOLDINGS})
    assert resp.status_code == 200
    body = resp.json()

    assert "rf=0" in body["risk_free"]
    assert "unavailable" in body["risk_free"].lower()
    # The annualized risk-free surfaced to the UI is exactly 0 in the fallback.
    assert body["risk_free_annual"] == 0.0


# --------------------------------------------------------------------------- #
# Feature A/B — the served dashboard wires up the example portfolio + drawdown
# --------------------------------------------------------------------------- #
def test_dashboard_wires_example_portfolio_and_drawdown(client):
    body = client.get("/").text

    # Feature A: single-source example portfolio constant + its tickers.
    assert "DEFAULT_PORTFOLIO" in body
    for ticker in ("PETR4.SA", "VALE3.SA", "HGLG11.SA"):
        assert ticker in body

    # Feature B: the drawdown chart and its percent-axis formatting are present.
    assert "drawdown-chart" in body
    assert "[feature B]" in body
