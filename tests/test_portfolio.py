"""Tests for the POST /portfolio/analyze endpoint."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app import main
from app.models import Price


def _seed_prices(session, ticker: str, closes: list[float]) -> None:
    start = date(2023, 1, 2)
    for i, c in enumerate(closes):
        d = start + timedelta(days=i)
        session.add(
            Price(
                ticker=ticker,
                date=d,
                open=c,
                high=c,
                low=c,
                close=c,
                adj_close=c,
                volume=1000.0,
            )
        )
    session.commit()


@pytest.fixture(autouse=True)
def _no_network_cdi(monkeypatch):
    # Keep the analyze endpoint offline by default; rf falls back cleanly.
    def boom(*a, **k):
        raise main.data.DataError("offline in tests")

    monkeypatch.setattr(main.data, "fetch_cdi", boom)


def test_analyze_basic(client, session):
    _seed_prices(session, "AAA.SA", [10, 11, 12, 11, 13])
    _seed_prices(session, "BBB.SA", [20, 20, 21, 22, 23])

    resp = client.post(
        "/portfolio/analyze",
        json={
            "holdings": [
                {"ticker": "AAA.SA", "weight": 1},
                {"ticker": "BBB.SA", "weight": 1},
            ],
            "risk_free_annual": 0.0,
        },
    )
    assert resp.status_code == 200
    body = resp.json()

    assert body["weights"] == {"AAA.SA": 0.5, "BBB.SA": 0.5}
    assert body["weights_normalized"] is True  # weights summed to 2
    assert set(body["assets"]) == {"AAA.SA", "BBB.SA"}
    assert body["correlation"]["AAA.SA"]["AAA.SA"] == 1.0
    assert "cumulative_return" in body["portfolio"]


def test_analyze_missing_ticker_400(client, session):
    _seed_prices(session, "AAA.SA", [10, 11, 12])
    resp = client.post(
        "/portfolio/analyze",
        json={"holdings": [{"ticker": "ZZZ.SA", "weight": 1}]},
    )
    assert resp.status_code == 400
    assert "ZZZ.SA" in resp.json()["detail"]


def test_analyze_cdi_fallback_note(client, session):
    _seed_prices(session, "AAA.SA", [10, 11, 12, 13])
    # No risk_free_annual -> tries CDI, which is mocked to fail -> rf=0 note.
    resp = client.post(
        "/portfolio/analyze",
        json={"holdings": [{"ticker": "AAA.SA", "weight": 1}]},
    )
    assert resp.status_code == 200
    assert "rf=0" in resp.json()["risk_free"]


def test_analyze_uses_cdi_when_available(client, session, monkeypatch):
    _seed_prices(session, "AAA.SA", [10, 11, 12, 13])

    def fake_cdi(start=None, end=None):
        return {date(2023, 1, 2): 0.0004, date(2023, 1, 3): 0.0004,
                date(2023, 1, 4): 0.0004, date(2023, 1, 5): 0.0004}

    monkeypatch.setattr(main.data, "fetch_cdi", fake_cdi)
    resp = client.post(
        "/portfolio/analyze",
        json={"holdings": [{"ticker": "AAA.SA", "weight": 1}]},
    )
    assert resp.status_code == 200
    assert "CDI" in resp.json()["risk_free"]
