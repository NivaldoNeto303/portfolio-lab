"""Tests for app.tickers search, with brapi.dev mocked (offline)."""

from __future__ import annotations

import pytest

from app import tickers


@pytest.fixture(autouse=True)
def _reset_cache():
    """Clear the in-memory brapi cache before each test for isolation."""
    tickers._cache["stocks"] = None
    tickers._cache["ts"] = 0.0
    yield


def _fake_universe(monkeypatch, codes):
    monkeypatch.setattr(tickers, "_fetch_universe", lambda: codes)


def test_empty_query_returns_curated():
    result = tickers.search("")
    assert result["source"] == "curated"
    assert result["tickers"] == tickers.CURATED_TICKERS[: len(result["tickers"])]


def test_prefix_matches_rank_before_substring(monkeypatch):
    _fake_universe(monkeypatch, ["APETR", "PETR4", "PETR3", "XPETRY"])
    result = tickers.search("petr")
    assert result["source"] == "brapi"
    # Prefix matches (sorted) come first, then substring matches (sorted).
    assert result["tickers"] == ["PETR3", "PETR4", "APETR", "XPETRY"]


def test_search_is_case_insensitive(monkeypatch):
    _fake_universe(monkeypatch, ["VALE3", "PETR4"])
    assert tickers.search("vale")["tickers"] == ["VALE3"]


def test_limit_is_respected(monkeypatch):
    _fake_universe(monkeypatch, [f"AAA{i}" for i in range(30)])
    result = tickers.search("aaa", limit=5)
    assert len(result["tickers"]) == 5


def test_offline_fallback_when_brapi_down(monkeypatch):
    monkeypatch.setattr(tickers, "_fetch_universe", lambda: None)
    result = tickers.search("petr")
    assert result["source"] == "offline"
    assert "PETR4" in result["tickers"]


def test_universe_is_cached(monkeypatch):
    calls = {"n": 0}

    def counting():
        calls["n"] += 1
        return ["PETR4", "VALE3"]

    monkeypatch.setattr(tickers, "_fetch_universe", counting)
    tickers.search("petr")
    tickers.search("vale")
    assert calls["n"] == 1  # second search hits the cache, not the network


def test_endpoint_returns_matches(client, monkeypatch):
    _fake_universe(monkeypatch, ["PETR4", "PETR3", "VALE3"])
    res = client.get("/tickers", params={"q": "petr"})
    assert res.status_code == 200
    assert res.json() == {"tickers": ["PETR3", "PETR4"], "source": "brapi"}
