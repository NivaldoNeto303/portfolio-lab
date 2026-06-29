"""Tests for the POST /backtest endpoint."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app import main
from app.models import Price


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


@pytest.fixture(autouse=True)
def _no_network_cdi(monkeypatch):
    def boom(*a, **k):
        raise main.data.DataError("offline in tests")

    monkeypatch.setattr(main.data, "fetch_cdi", boom)


def test_backtest_ma_crossover(client, session):
    _seed_prices(session, "AAA.SA", [float(i) for i in range(1, 31)])
    resp = client.post(
        "/backtest",
        json={
            "strategy": "ma_crossover",
            "ticker": "AAA.SA",
            "short_window": 3,
            "long_window": 6,
            "risk_free_annual": 0.0,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["strategy_name"] == "ma_crossover"
    assert "metrics" in body["strategy"] and "equity" in body["strategy"]
    assert len(body["dates"]) == len(body["strategy"]["equity"])


def test_backtest_ma_crossover_requires_ticker(client):
    resp = client.post("/backtest", json={"strategy": "ma_crossover"})
    assert resp.status_code == 400


def test_backtest_bad_windows_400(client, session):
    _seed_prices(session, "AAA.SA", [float(i) for i in range(1, 31)])
    resp = client.post(
        "/backtest",
        json={"strategy": "ma_crossover", "ticker": "AAA.SA",
              "short_window": 10, "long_window": 5},
    )
    assert resp.status_code == 400


def test_backtest_monthly_rebalance(client, session):
    _seed_prices(session, "AAA.SA", [100 + i for i in range(70)])
    _seed_prices(session, "BBB.SA", [50 + i * 0.5 for i in range(70)])
    resp = client.post(
        "/backtest",
        json={
            "strategy": "monthly_rebalance",
            "holdings": [
                {"ticker": "AAA.SA", "weight": 0.5},
                {"ticker": "BBB.SA", "weight": 0.5},
            ],
            "risk_free_annual": 0.0,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["weights"] == {"AAA.SA": 0.5, "BBB.SA": 0.5}
    assert len(body["strategy"]["equity"]) == len(body["buy_and_hold"]["equity"])


def test_backtest_missing_ticker_400(client, session):
    resp = client.post(
        "/backtest",
        json={"strategy": "monthly_rebalance",
              "holdings": [{"ticker": "ZZZ.SA", "weight": 1}]},
    )
    assert resp.status_code == 400
    assert "ZZZ.SA" in resp.json()["detail"]
