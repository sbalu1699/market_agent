"""Bullion / precious metals weekly and monthly analysis."""

from __future__ import annotations

from dataclasses import asdict

from .analyzer import (
    MIN_PRICE,
    StockMetrics,
    _compute_metrics,
    _passes_monthly_filters,
    _passes_weekly_filters,
)
from .market_data import fetch_stock_history

# Core bullion market — physical precious metal ETFs (always shown in overview)
BULLION_MARKET_UNIVERSE: dict[str, str] = {
    "GLD": "Gold",
    "SLV": "Silver",
    "PPLT": "Platinum",
    "PALL": "Palladium",
}

# Major gold / silver / PGM miners and royalty names
BULLION_STOCK_UNIVERSE: dict[str, str] = {
    "NEM": "Newmont Corporation",
    "GOLD": "Barrick Gold",
    "AEM": "Agnico Eagle Mines",
    "FNV": "Franco-Nevada",
    "WPM": "Wheaton Precious Metals",
    "RGLD": "Royal Gold",
    "KGC": "Kinross Gold",
    "GFI": "Gold Fields",
    "AU": "AngloGold Ashanti",
    "PAAS": "Pan American Silver",
    "AG": "First Majestic Silver",
    "HL": "Hecla Mining",
    "CDE": "Coeur Mining",
    "FSM": "Fortuna Silver Mines",
    "SBSW": "Sibanye-Stillwater",
    "NGD": "New Gold",
    "EQX": "Equinox Gold",
    "IAG": "IAMGOLD",
    "SSRM": "SSR Mining",
    "FCX": "Freeport-McMoRan",
    "TECK": "Teck Resources",
    "SCCO": "Southern Copper",
}

# Physical bullion, miner, and diversified precious-metal ETFs
BULLION_ETF_UNIVERSE: dict[str, str] = {
    "GLD": "SPDR Gold Shares",
    "IAU": "iShares Gold Trust",
    "SGOL": "abrdn Physical Gold",
    "SLV": "iShares Silver Trust",
    "SIVR": "abrdn Physical Silver",
    "PPLT": "abrdn Physical Platinum",
    "PALL": "abrdn Physical Palladium",
    "GDX": "VanEck Gold Miners",
    "GDXJ": "VanEck Junior Gold Miners",
    "SIL": "Global X Silver Miners",
    "SILJ": "ETFMG Junior Silver Miners",
    "GOAU": "US Global GO Gold & Precious Miners",
    "RING": "iShares MSCI Global Gold Miners",
    "DBP": "Invesco DB Precious Metals",
    "GLDM": "SPDR Gold MiniShares",
    "OUNZ": "VanEck Merk Gold",
    "BAR": "GraniteShares Gold Trust",
    "PSLV": "Sprott Physical Silver",
    "REMX": "VanEck Rare Earth & Strategic Metals",
    "COPX": "Global X Copper Miners",
}

# Precious metals and mining mutual funds
BULLION_MUTUAL_FUND_UNIVERSE: dict[str, str] = {
    "FSAGX": "Fidelity Select Gold Portfolio",
    "FGLDX": "Fidelity Advisor Gold Fund",
    "INIVX": "Franklin Gold and Precious Metals",
    "USAGX": "US Global Gold and Precious Metals",
    "OPGSX": "Invesco Gold & Special Minerals",
    "BGEIX": "BlackRock Gold & Special Minerals",
    "SGGDX": "Sprott Gold Equity Fund",
    "VGPMX": "Vanguard Global Capital Cycles",
    "TGLDX": "Tocqueville Gold Fund",
    "AAEMX": "Alpine Global Mining & Metals",
    "UNWPX": "US Global World Precious Minerals",
}


def _passes_weekly_fund_filters(metrics: StockMetrics) -> bool:
    """Mutual funds: same period/price rules as stocks; skip volume (yfinance reports 0)."""
    return (
        metrics.price >= MIN_PRICE
        and metrics.week_change_pct is not None
        and metrics.week_change_pct > 0
    )


def _passes_monthly_fund_filters(metrics: StockMetrics) -> bool:
    return (
        metrics.price >= MIN_PRICE
        and metrics.month_change_pct is not None
        and metrics.month_change_pct > 0
    )


def _collect_filtered(
    tickers: dict[str, str],
    filter_fn,
    sort_key: str,
    top_n: int,
    history: dict | None = None,
    sector: str = "Bullion",
) -> list[dict]:
    """Rank tickers that pass the same filters used for S&P 500 stocks."""
    if history is None:
        history = fetch_stock_history(list(tickers.keys()))

    qualified: list[StockMetrics] = []
    for ticker in tickers:
        frame = history.get(ticker)
        if frame is None or frame.empty:
            continue
        metrics = _compute_metrics(
            ticker, frame, name=tickers[ticker], sector=sector
        )
        if metrics and filter_fn(metrics):
            qualified.append(metrics)

    qualified.sort(key=lambda m: getattr(m, sort_key) or -999, reverse=True)
    return [asdict(m) for m in qualified[:top_n]]


def _collect_all(
    tickers: dict[str, str],
    sort_key: str,
    history: dict | None = None,
    sector: str = "Bullion",
) -> list[dict]:
    """Return all tickers with metrics, sorted by period (for market overview)."""
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


def get_bullion_market_overview(
    period: str = "weekly",
    history: dict | None = None,
) -> list[dict]:
    """All four precious metals with period returns (overview table)."""
    sort_key = "week_change_pct" if period == "weekly" else "month_change_pct"
    return _collect_all(BULLION_MARKET_UNIVERSE, sort_key, history, sector="Metal")


def analyze_bullion_stocks_weekly(
    top_n: int = 20, history: dict | None = None
) -> list[dict]:
    return _collect_filtered(
        BULLION_STOCK_UNIVERSE,
        _passes_weekly_filters,
        "week_change_pct",
        top_n,
        history,
        sector="Bullion Stock",
    )


def analyze_bullion_stocks_monthly(
    top_n: int = 20, history: dict | None = None
) -> list[dict]:
    return _collect_filtered(
        BULLION_STOCK_UNIVERSE,
        _passes_monthly_filters,
        "month_change_pct",
        top_n,
        history,
        sector="Bullion Stock",
    )


def analyze_bullion_etfs_weekly(
    top_n: int = 20, history: dict | None = None
) -> list[dict]:
    return _collect_filtered(
        BULLION_ETF_UNIVERSE,
        _passes_weekly_filters,
        "week_change_pct",
        top_n,
        history,
        sector="Bullion ETF",
    )


def analyze_bullion_etfs_monthly(
    top_n: int = 20, history: dict | None = None
) -> list[dict]:
    return _collect_filtered(
        BULLION_ETF_UNIVERSE,
        _passes_monthly_filters,
        "month_change_pct",
        top_n,
        history,
        sector="Bullion ETF",
    )


def analyze_bullion_mutual_funds_weekly(
    top_n: int = 20, history: dict | None = None
) -> list[dict]:
    return _collect_filtered(
        BULLION_MUTUAL_FUND_UNIVERSE,
        _passes_weekly_fund_filters,
        "week_change_pct",
        top_n,
        history,
        sector="Bullion Fund",
    )


def analyze_bullion_mutual_funds_monthly(
    top_n: int = 20, history: dict | None = None
) -> list[dict]:
    return _collect_filtered(
        BULLION_MUTUAL_FUND_UNIVERSE,
        _passes_monthly_fund_filters,
        "month_change_pct",
        top_n,
        history,
        sector="Bullion Fund",
    )
