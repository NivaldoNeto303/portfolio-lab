"""B3 ticker lookup for the autocomplete search box.

The universe of tradable B3 symbols is fetched once from brapi.dev's free,
token-less ``/available`` endpoint and cached in memory (see ``_TTL``); each
search then filters that cached list locally, so typing is instant and does not
hit the network per keystroke. If brapi is unreachable we fall back to a small
curated list of liquid names, so the feature degrades gracefully offline.

brapi.dev returns bare codes (e.g. ``PETR4``); callers append the ``.SA`` Yahoo
suffix when syncing, matching the rest of the app.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

# Free, no token required. Returns {"stocks": [...], "indexes": [...]}.
BRAPI_AVAILABLE_URL = "https://brapi.dev/api/available"

# Offline fallback — a curated set of liquid B3 stocks and popular FIIs. Also
# used to seed the dropdown before the user has typed anything.
CURATED_TICKERS: list[str] = [
    # Blue-chip stocks
    "PETR4", "PETR3", "VALE3", "ITUB4", "BBDC4", "BBAS3", "B3SA3", "ABEV3",
    "WEGE3", "ITSA4", "SANB11", "BPAC11", "RENT3", "SUZB3", "RADL3", "EQTL3",
    "PRIO3", "RAIL3", "GGBR4", "CSNA3", "USIM5", "CMIG4", "ELET3", "ELET6",
    "SBSP3", "VBBR3", "UGPA3", "LREN3", "MGLU3", "AMER3", "NTCO3", "HAPV3",
    "RDOR3", "TOTS3", "VIVT3", "TIMS3", "EMBR3", "AZUL4", "CCRO3", "KLBN11",
    "GOAU4", "BRFS3", "JBSS3", "MRFG3", "CPLE6", "TAEE11", "EGIE3", "FLRY3",
    # Popular FIIs
    "HGLG11", "KNRI11", "MXRF11", "HGRE11", "XPLG11", "VISC11", "HGBS11",
    "BCFF11", "KNCR11", "IRDM11", "XPML11", "VGHF11", "RECR11", "HGRU11",
]

# Simple in-memory cache of the full brapi universe.
_TTL = 60 * 60 * 24  # 24h
_cache: dict[str, object] = {"stocks": None, "ts": 0.0}


def _fetch_universe() -> list[str] | None:
    """Fetch the full list of available B3 codes from brapi.dev.

    Returns the list of stock codes, or ``None`` on any network/parse error so
    the caller can fall back to the curated list.
    """
    try:
        req = urllib.request.Request(
            BRAPI_AVAILABLE_URL, headers={"User-Agent": "portfolio-lab"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None

    stocks = raw.get("stocks") if isinstance(raw, dict) else None
    if not isinstance(stocks, list) or not stocks:
        return None
    return [str(s).upper() for s in stocks]


def _universe() -> tuple[list[str], str]:
    """Return ``(codes, source)`` where source is ``"brapi"`` or ``"offline"``.

    Uses the cached brapi list when fresh; otherwise refetches. Falls back to
    the curated list (and does not poison the cache) when brapi is unreachable.
    """
    now = time.time()
    cached = _cache.get("stocks")
    if isinstance(cached, list) and now - float(_cache["ts"]) < _TTL:
        return cached, "brapi"

    fetched = _fetch_universe()
    if fetched is not None:
        _cache["stocks"] = fetched
        _cache["ts"] = now
        return fetched, "brapi"

    # brapi down: use a stale cache if we have one, else the curated list.
    if isinstance(cached, list):
        return cached, "brapi"
    return CURATED_TICKERS, "offline"


def search(query: str, limit: int = 15) -> dict[str, object]:
    """Search the B3 universe for ``query`` (case-insensitive substring).

    Prefix matches rank above mid-string matches, then alphabetical. An empty
    query returns the curated popular list so the dropdown is useful on focus.
    Returns ``{"tickers": [...], "source": "brapi"|"offline"}``.
    """
    q = query.strip().upper()
    if not q:
        return {"tickers": CURATED_TICKERS[:limit], "source": "curated"}

    codes, source = _universe()
    prefix = [c for c in codes if c.startswith(q)]
    contains = [c for c in codes if q in c and not c.startswith(q)]
    ordered = sorted(prefix) + sorted(contains)
    return {"tickers": ordered[:limit], "source": source}
