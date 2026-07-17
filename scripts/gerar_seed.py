"""Generate the versioned seed file for the dashboard's example portfolio.

Downloads real daily history for the default portfolio (mirrors DEFAULT_PORTFOLIO
in ``app/templates/dashboard.html``) through the existing data layer and writes
it to ``app/seed_data/example_prices.csv``, which is committed so the app can
render the example offline (Render's disk is ephemeral and yfinance is often
blocked from datacenter IPs).

Run locally, from the repo root, where the network is available:

    python scripts/gerar_seed.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

# Allow running as a plain script (``python scripts/gerar_seed.py``) from root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import data  # noqa: E402

# Mirror DEFAULT_PORTFOLIO in app/templates/dashboard.html.
EXAMPLE_TICKERS = ["PETR4.SA", "VALE3.SA", "HGLG11.SA"]
START = "2021-01-01"

OUT = Path(__file__).resolve().parent.parent / "app" / "seed_data" / "example_prices.csv"
FIELDS = ["ticker", "date", "open", "high", "low", "close", "adj_close", "volume"]


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        for ticker in EXAMPLE_TICKERS:
            rows = data.fetch_history(ticker, start=START)
            for r in rows:
                writer.writerow(
                    {
                        "ticker": ticker,
                        "date": r.date.isoformat(),
                        "open": r.open,
                        "high": r.high,
                        "low": r.low,
                        "close": r.close,
                        "adj_close": r.adj_close,
                        "volume": r.volume,
                    }
                )
            total += len(rows)
            print(f"  {ticker}: {len(rows)} rows")
    print(f"Wrote {total} rows -> {OUT}")


if __name__ == "__main__":
    main()
