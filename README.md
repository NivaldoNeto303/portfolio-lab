# Portfolio Lab

A small web application for analyzing and backtesting equity and REIT (FII)
portfolios on the Brazilian stock exchange (B3). You define a portfolio of
tickers, the app fetches historical prices, computes risk/return metrics, and
runs simple strategy backtests, all visualized in a dashboard.

> This is a portfolio project meant to demonstrate backend/data-engineering
> skills together with financial-domain knowledge. See [`SPEC.md`](SPEC.md) for
> the full design.

## Status

Built in phases:

- [x] **Phase 1 — Data layer:** fetch & persist historical daily prices, with
  idempotent syncs.
- [ ] Phase 2 — Portfolio metrics (return, volatility, Sharpe, drawdown,
  correlation).
- [ ] Phase 3 — Backtester (strategy vs. buy-and-hold).
- [ ] Phase 4 — Dashboard (Chart.js) & polish.

## Tech stack

- Python 3.11+
- FastAPI + Uvicorn
- SQLite via SQLModel
- `yfinance` for historical OHLCV data (B3 tickers use the `.SA` suffix, e.g.
  `PETR4.SA`, `HGLG11.SA`)
- pytest

## How to run

```bash
# 1. Create a virtual environment and install dependencies
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. Start the API (creates portfolio_lab.db on first run)
uvicorn app.main:app --reload
```

The API is then available at `http://127.0.0.1:8000`, with interactive docs at
`http://127.0.0.1:8000/docs`.

## API (Phase 1)

| Method | Path                              | Description                                  |
| ------ | --------------------------------- | -------------------------------------------- |
| `POST` | `/assets/{ticker}/sync`           | Fetch from yfinance and upsert into the DB.  |
| `GET`  | `/assets/{ticker}/prices`         | Return the stored price series (`start`/`end` optional). |
| `GET`  | `/assets`                         | List tracked tickers.                        |

Example:

```bash
# Sync ~1 year of Petrobras prices, then read them back
curl -X POST "http://127.0.0.1:8000/assets/PETR4.SA/sync?start=2023-01-01"
curl "http://127.0.0.1:8000/assets/PETR4.SA/prices?start=2023-01-01"
curl "http://127.0.0.1:8000/assets"
```

Syncs are idempotent: re-running a sync updates existing rows instead of
duplicating them (unique constraint on `(ticker, date)`).

## Tests

```bash
pytest
```

Tests mock yfinance, so they run offline.
