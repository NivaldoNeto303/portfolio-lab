"""Tests for app.data.fetch_history, with yfinance mocked (offline)."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from app import data


def _fake_frame() -> pd.DataFrame:
    idx = pd.to_datetime(["2023-01-02", "2023-01-03"])
    return pd.DataFrame(
        {
            "Open": [10.0, 11.0],
            "High": [10.5, 11.5],
            "Low": [9.5, 10.5],
            "Close": [10.2, 11.2],
            "Adj Close": [10.0, 11.0],
            "Volume": [1000.0, 2000.0],
        },
        index=idx,
    )


def test_fetch_history_maps_rows(monkeypatch):
    monkeypatch.setattr(data.yf, "download", lambda *a, **k: _fake_frame())

    rows = data.fetch_history("PETR4.SA", start="2023-01-01")

    assert len(rows) == 2
    assert rows[0].date == date(2023, 1, 2)
    assert rows[0].close == 10.2
    assert rows[1].adj_close == 11.0


def test_fetch_history_empty_raises(monkeypatch):
    monkeypatch.setattr(data.yf, "download", lambda *a, **k: pd.DataFrame())

    with pytest.raises(data.DataError):
        data.fetch_history("NOPE.SA")


def test_fetch_history_network_error_raises(monkeypatch):
    def boom(*a, **k):
        raise ConnectionError("network down")

    monkeypatch.setattr(data.yf, "download", boom)

    with pytest.raises(data.DataError):
        data.fetch_history("PETR4.SA")


def test_fetch_history_drops_nan_close(monkeypatch):
    frame = _fake_frame()
    frame.loc[frame.index[1], "Close"] = float("nan")
    monkeypatch.setattr(data.yf, "download", lambda *a, **k: frame)

    rows = data.fetch_history("PETR4.SA")

    assert len(rows) == 1
    assert rows[0].date == date(2023, 1, 2)
