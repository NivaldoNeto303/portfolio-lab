# Portfolio Lab — Project Spec

> Single source of truth for this project. Read this fully before writing or
> changing code. When something here is ambiguous, ask before assuming.

## 1. Overview

Portfolio Lab is a small web application for analyzing and backtesting equity
and REIT (FII) portfolios on the Brazilian stock exchange (B3). A user defines
a portfolio of tickers, the app fetches historical prices, computes
risk/return metrics, and runs simple strategy backtests, all visualized in a
dashboard.

This is a portfolio project meant to demonstrate two skills at once:
backend/data engineering **and** financial-domain knowledge. Code quality,
clarity, and a clean README matter as much as features.

## 2. Goals & non-goals

**Goals**
- Fetch and persist historical daily prices for B3 assets.
- Compute portfolio metrics: cumulative return, volatility, Sharpe ratio,
  max drawdown, correlation matrix.
- Backtest a simple strategy (e.g. moving-average crossover and/or monthly
  rebalancing) and compare it against buy-and-hold.
- Present everything in a clean dashboard (Chart.js).

**Non-goals (out of scope for now)**
- Real-money trading, brokerage integration, or order execution.
- User accounts / authentication.
- Intraday or real-time tick data.
- Tax (IRPF) calculation.

## 3. Tech stack

- **Language:** Python 3.11+
- **API:** FastAPI + Uvicorn
- **DB:** SQLite via SQLModel
- **Historical data:** `yfinance` (B3 tickers use the `.SA` suffix, e.g.
  `PETR4.SA`, `HGLG11.SA`). Use this for long historical OHLCV series.
- **Quotes / dividends / fundamentals (later phases):** brapi.dev REST API
  (`pip install brapi`). Free tier; a token is needed for broader coverage.
- **Charts:** Chart.js (served from a simple Jinja2 template or a static page).
- **Tests:** pytest.

## 4. Architecture

```
app/
  main.py        # FastAPI app + routes
  db.py          # engine, session, init
  models.py      # SQLModel tables
  data.py        # data fetching (yfinance now, brapi later)
  metrics.py     # return/risk calculations (phase 2)
  backtest.py    # strategy backtester (phase 3)
  templates/     # dashboard (phase 4)
tests/
SPEC.md
README.md        # in English
```

## 5. Data model

- **Asset**: `id`, `ticker` (unique), `name`, `kind` (stock | fii),
  `created_at`.
- **Price**: `id`, `ticker`, `date`, `open`, `high`, `low`, `close`,
  `adj_close`, `volume`. Unique constraint on `(ticker, date)` so re-syncing
  is idempotent (upsert, never duplicate).

## 6. Roadmap (build in this order, one phase per chunk of work)

**Phase 1 — Data layer**
- Project scaffold, repo, dependencies, README skeleton (English).
- `data.fetch_history(ticker, start)` using yfinance.
- SQLite schema + idempotent upsert.
- Endpoints:
  - `POST /assets/{ticker}/sync` — fetch from yfinance, upsert into DB.
  - `GET  /assets/{ticker}/prices?start=&end=` — return stored series.
  - `GET  /assets` — list tracked tickers.

**Phase 2 — Portfolio metrics**
- Define a portfolio as a set of tickers with weights.
- Compute: cumulative return, annualized volatility, Sharpe ratio,
  max drawdown, correlation matrix.
- Endpoint: `POST /portfolio/analyze`.

**Phase 3 — Backtester**
- Implement a simple strategy (moving-average crossover and/or monthly
  rebalancing).
- Run against historical data; compare strategy vs. buy-and-hold.
- Report key metrics for both.
- Endpoint: `POST /backtest`.

**Phase 4 — Dashboard & polish**
- Chart.js views: equity curve, drawdown, allocation, correlation heatmap.
- Finish README in English (problem, screenshots, how to run).
- Deploy (or clear local run instructions).

## 7. Conventions

- **Everything in English**: code, comments, commit messages, README, docs.
- **Small, focused commits** with clear messages.
- **Idempotency**: data syncs must be safe to re-run.
- **Error handling**: handle network failures, unknown tickers, and empty
  responses gracefully — no bare crashes.
- **Tests**: write pytest tests for metrics and backtest logic (the financial
  math is where correctness matters most).
- **No secrets in the repo**: API tokens via environment variables / `.env`
  (and `.env` in `.gitignore`).

## 8. How to work with me (instructions for Claude Code)

1. **Plan before coding.** For each phase, propose a short plan and wait for
   approval before writing code.
2. **One phase at a time.** Do not scaffold all four phases at once.
3. **Explain your choices.** When you make a non-obvious decision, say why in
   one or two sentences — I need to understand this code well enough to defend
   it in a job interview.
4. **Ask, don't assume.** If the spec is ambiguous, ask a focused question.
5. **Keep the README current** as features land.
