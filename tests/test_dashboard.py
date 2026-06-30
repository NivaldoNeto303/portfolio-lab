"""Smoke test for the Phase 4 dashboard route."""

from __future__ import annotations


def test_dashboard_served(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    body = resp.text
    # Key building blocks of the page are present.
    assert "Portfolio Lab" in body
    assert "equity-chart" in body
    assert "correlation" in body
    assert "cdn.jsdelivr.net/npm/chart.js" in body
