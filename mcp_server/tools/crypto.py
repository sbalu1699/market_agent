"""Bitcoin / crypto ETF analysis for broad market reports (not bullion)."""

from __future__ import annotations

from dataclasses import asdict

from .analyzer import StockMetrics, _compute_metrics
from .market_data import fetch_stock_history

# Spot Bitcoin & Ethereum proxies for overview row
CRYPTO_OVERVIEW_UNIVERSE: dict[str, str] = {
    "IBIT": "Bitcoin",
    "ETHA": "Ethereum",
}

# Bitcoin, Ethereum, miners, and thematic crypto ETFs (separate from broad ETF_UNIVERSE)
CRYPTO_ETF_UNIVERSE: dict[str, str] = {
    # --- Spot Bitcoin ---
    "IBIT": "iShares Bitcoin Trust",
    "FBTC": "Fidelity Wise Origin Bitcoin",
    "GBTC": "Grayscale Bitcoin Trust",
    "BITB": "Bitwise Bitcoin ETF",
    "ARKB": "ARK 21Shares Bitcoin",
    "BTC": "Grayscale Bitcoin Mini",
    "HODL": "VanEck Bitcoin Trust",
    "EZBC": "Franklin Bitcoin ETF",
    "BRRR": "Coinshares Valkyrie Bitcoin",
    # --- Spot Ethereum ---
    "ETHA": "iShares Ethereum Trust",
    "FETH": "Fidelity Ethereum Fund",
    "ETHE": "Grayscale Ethereum Trust",
    "ETHW": "Bitwise Ethereum ETF",
    "QETH": "Invesco Galaxy Ethereum",
    # --- Crypto equities / miners / thematic ---
    "BITQ": "Bitwise Crypto Industry Innovators",
    "BLOK": "Amplify Transformational Data",
    "WGMI": "Valkyrie Bitcoin Miners",
    "DAPP": "VanEck Digital Transformation",
    "BITO": "ProShares Bitcoin Strategy (futures)",
    "DEFI": "Hashdex Bitcoin ETF",
    "BTCW": "WisdomTree Bitcoin Fund",
}


def _collect_all(
    tickers: dict[str, str],
    sort_key: str,
    history: dict | None = None,
    sector: str = "Crypto",
) -> list[dict]:
    if history is None:
        history = fetch_stock_history(list(tickers.keys()))
    results: list[StockMetrics] = []
    for ticker in tickers:
        frame = history.get(ticker)
        if frame is None or frame.empty:
            continue
        metrics = _compute_metrics(
            ticker, frame, name=tickers[ticker], sector=sector
        )
        if metrics:
            results.append(metrics)
    results.sort(key=lambda m: getattr(m, sort_key) or -999, reverse=True)
    return [asdict(m) for m in results]


def _rank_top(
    tickers: dict[str, str],
    sort_key: str,
    top_n: int,
    history: dict | None = None,
) -> list[dict]:
    return _collect_all(tickers, sort_key, history)[:top_n]


def get_crypto_overview(
    period: str = "daily",
    history: dict | None = None,
    variant: str = "day",
) -> list[dict]:
    if period == "daily" and variant == "momentum":
        sort_key = "return_1m"
    else:
        sort_keys = {
            "daily": "day_change_pct",
            "weekly": "week_change_pct",
            "monthly": "month_change_pct",
        }
        sort_key = sort_keys.get(period, "day_change_pct")
    return _collect_all(
        CRYPTO_OVERVIEW_UNIVERSE,
        sort_key,
        history,
        sector="Crypto",
    )


def analyze_top_crypto_etfs(
    top_n: int = 20,
    history: dict | None = None,
    sort_key: str = "day_change_pct",
) -> list[dict]:
    return _rank_top(CRYPTO_ETF_UNIVERSE, sort_key, top_n, history)


def analyze_top_crypto_etfs_weekly(top_n: int = 20, history: dict | None = None) -> list[dict]:
    return _rank_top(CRYPTO_ETF_UNIVERSE, "week_change_pct", top_n, history)


def analyze_top_crypto_etfs_monthly(top_n: int = 20, history: dict | None = None) -> list[dict]:
    return _rank_top(CRYPTO_ETF_UNIVERSE, "month_change_pct", top_n, history)


def analyze_top_crypto_etfs_momentum(top_n: int = 20, history: dict | None = None) -> list[dict]:
    return _rank_top(CRYPTO_ETF_UNIVERSE, "return_1m", top_n, history)
