"""End-to-end API tests, with the yfinance fetch mocked.

The headline test is idempotency: syncing the same ticker twice must not
duplicate rows (SPEC.md section 7).
"""

from __future__ import annotations

from datetime import date

import pytest

from app import data, main
from app.models import Price
from sqlmodel import select


def _fake_rows() -> list[data.PriceRow]:
    return [
        data.PriceRow(date(2023, 1, 2), 10.0, 10.5, 9.5, 10.2, 10.0, 1000.0),
        data.PriceRow(date(2023, 1, 3), 11.0, 11.5, 10.5, 11.2, 11.0, 2000.0),
    ]


@pytest.fixture(autouse=True)
def _mock_fetch(monkeypatch):
    monkeypatch.setattr(main.data, "fetch_history", lambda ticker, start=None: _fake_rows())


def test_sync_then_read_prices(client):
    resp = client.post("/assets/PETR4.SA/sync")
    assert resp.status_code == 200
    assert resp.json()["rows_synced"] == 2

    resp = client.get("/assets/PETR4.SA/prices")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert body[0]["close"] == 10.2


def test_sync_is_idempotent(client, session):
    client.post("/assets/PETR4.SA/sync")
    client.post("/assets/PETR4.SA/sync")  # second run must not duplicate

    rows = session.exec(select(Price).where(Price.ticker == "PETR4.SA")).all()
    assert len(rows) == 2


def test_sync_registers_asset_once(client):
    client.post("/assets/PETR4.SA/sync")
    client.post("/assets/PETR4.SA/sync")

    assets = client.get("/assets").json()
    tickers = [a["ticker"] for a in assets]
    assert tickers == ["PETR4.SA"]


def test_fii_kind_inferred(client):
    client.post("/assets/HGLG11.SA/sync")
    assets = client.get("/assets").json()
    assert assets[0]["kind"] == "fii"


def test_prices_date_filter(client):
    client.post("/assets/PETR4.SA/sync")
    resp = client.get("/assets/PETR4.SA/prices", params={"start": "2023-01-03"})
    body = resp.json()
    assert len(body) == 1
    assert body[0]["date"] == "2023-01-03"


def test_prices_unknown_ticker_404(client):
    resp = client.get("/assets/UNKNOWN.SA/prices")
    assert resp.status_code == 404


def test_sync_data_error_returns_502(client, monkeypatch):
    def boom(ticker, start=None):
        raise data.DataError("unknown ticker")

    monkeypatch.setattr(main.data, "fetch_history", boom)
    resp = client.post("/assets/NOPE.SA/sync")
    assert resp.status_code == 502
