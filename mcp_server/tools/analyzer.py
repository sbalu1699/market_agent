"""Moving-average analysis and top-performer filtering."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass

import pandas as pd

from .market_data import (
    TRADING_DAYS_1M,
    TRADING_DAYS_1W,
    TRADING_DAYS_2M,
    TRADING_DAYS_6M,
    TRADING_DAYS_52W,
    calc_ytd_change,
    fetch_stock_history,
)

logger = logging.getLogger(__name__)

MIN_PRICE = 2.0
MIN_AVG_VOLUME = 500_000

# Broad market, all GICS sectors, semiconductors, sub-industry, thematic, international
ETF_UNIVERSE = list(dict.fromkeys([
    # --- Broad US market ---
    "SPY", "QQQ", "IWM", "DIA", "VTI", "VOO", "SCHB", "ITOT", "MDY", "IJH", "IJR", "RSP",
    # --- SPDR sector (11 GICS) ---
    "XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLRE", "XLB", "XLC",
    # --- Vanguard sector ---
    "VGT", "VFH", "VDE", "VHT", "VIS", "VCR", "VDC", "VPU", "VNQ", "VAW", "VOX",
    # --- Semiconductors & technology ---
    "SMH", "SOXX", "XSD", "PSI", "DRAM", "IGV", "SKYY", "WCLD", "CLOU", "HACK",
    "BOTZ", "ROBO", "AIQ", "CHAT", "ARKK", "ARKW", "IGM", "IYW",
    # --- Financials, energy, healthcare sub-sectors ---
    "KBE", "KRE", "IAI", "XOP", "OIH", "AMLP", "XBI", "IBB", "XPH", "XHE",
    # --- Industrials, consumer, materials ---
    "PAVE", "IFRA", "IYT", "XRT", "XHB", "PEJ", "GDX", "GDXJ", "SLX", "REMX", "COPX",
    # --- Clean energy & EV ---
    "ICLN", "QCLN", "TAN", "FAN", "PBW", "ACES", "CNRG", "SMOG", "LIT", "DRIV", "GRID",
    # --- International ---
    "EFA", "EEM", "VEA", "VWO", "IEMG", "FXI", "EWJ", "EWZ", "INDA",
]))

MUTUAL_FUND_UNIVERSE: dict[str, str] = {
    # --- Broad index ---
    "VFINX": "Vanguard 500 Index Fund",
    "FXAIX": "Fidelity 500 Index Fund",
    "SWPPX": "Schwab S&P 500 Index Fund",
    "VTSAX": "Vanguard Total Stock Market",
    "AGTHX": "American Funds Growth Fund of America",
    "PRGFX": "T. Rowe Price Growth Stock Fund",
    "VIGAX": "Vanguard Growth Index",
    "VIMAX": "Vanguard Mid-Cap Index",
    "VSMAX": "Vanguard Small-Cap Index",
    # --- Sector / industry (Fidelity Select) ---
    "FSMKX": "Fidelity Select Semiconductors",
    "FSPTX": "Fidelity Select Technology",
    "FSENX": "Fidelity Select Energy",
    "FSHCX": "Fidelity Select Health Care",
    "FSCSX": "Fidelity Select Software",
    "FBMPX": "Fidelity Select Materials",
    "FBIOX": "Fidelity Select Biotechnology",
    "FSRFX": "Fidelity Select Financial Services",
    "FSPCX": "Fidelity Select Insurance",
    "FSCHX": "Fidelity Select Consumer Staples",
    "FCDIX": "Fidelity Select Consumer Discretionary",
    "FSUTX": "Fidelity Select Utilities",
    "FSHOX": "Fidelity Select Housing",
    "FSRRX": "Fidelity Select Transportation",
    "FSLDX": "Fidelity Select Industrials",
    # --- Clean energy / thematic ---
    "NALFX": "New Alternatives Fund",
    "FSLEX": "Fidelity Select Environment & Alt Energy",
    "CGAEX": "Calvert Global Energy Solutions",
    "GAAEX": "Guinness Atkinson Alternative Energy",
    "FCEAX": "Firsthand Alternative Energy",
}


@dataclass
class StockMetrics:
    ticker: str
    name: str
    sector: str
    price: float
    day_change_dollar: float | None
    day_change_pct: float | None
    week_change_dollar: float | None
    week_change_pct: float | None
    month_change_dollar: float | None
    month_change_pct: float | None
    ytd_change_dollar: float | None
    ytd_change_pct: float | None
    return_1m: float
    return_2m: float
    return_6m: float | None
    week52_high: float | None
    week52_low: float | None
    ma20: float
    ma50: float
    ma60: float
    ma200: float | None
    avg_volume: float
    above_ma20: bool
    above_ma50: bool
    above_ma60: bool


def _calc_return(close: pd.Series, days: int) -> float | None:
    if len(close) < days + 1:
        return None
    start = close.iloc[-days - 1]
    end = close.iloc[-1]
    if start == 0:
        return None
    return float((end / start - 1) * 100)


def _calc_day_change(close: pd.Series, price: float) -> tuple[float | None, float | None]:
    if len(close) < 2:
        return None, None
    prev = float(close.iloc[-2])
    if prev == 0:
        return None, None
    dollar = price - prev
    pct = (price / prev - 1) * 100
    return dollar, pct


def _calc_week_change(close: pd.Series, price: float) -> tuple[float | None, float | None]:
    if len(close) < TRADING_DAYS_1W + 1:
        return None, None
    prev = float(close.iloc[-TRADING_DAYS_1W - 1])
    if prev == 0:
        return None, None
    dollar = price - prev
    pct = _calc_return(close, TRADING_DAYS_1W)
    return dollar, pct


def _calc_month_change(close: pd.Series, price: float) -> tuple[float | None, float | None]:
    if len(close) < TRADING_DAYS_1M + 1:
        return None, None
    prev = float(close.iloc[-TRADING_DAYS_1M - 1])
    if prev == 0:
        return None, None
    dollar = price - prev
    pct = _calc_return(close, TRADING_DAYS_1M)
    return dollar, pct


def _calc_52w_range(frame: pd.DataFrame) -> tuple[float | None, float | None]:
    window = frame.tail(min(TRADING_DAYS_52W, len(frame)))
    if window.empty:
        return None, None
    if "High" in window.columns and "Low" in window.columns:
        return float(window["High"].max()), float(window["Low"].min())
    close = window["Close"]
    return float(close.max()), float(close.min())


def _compute_metrics(
    ticker: str,
    frame: pd.DataFrame,
    name: str = "",
    sector: str = "",
) -> StockMetrics | None:
    try:
        close = frame["Close"]
        volume = frame.get("Volume", pd.Series(dtype=float))

        if len(close) < 60:
            return None

        price = float(close.iloc[-1])
        ma20 = float(close.rolling(20).mean().iloc[-1])
        ma50 = float(close.rolling(50).mean().iloc[-1])
        ma60 = float(close.rolling(60).mean().iloc[-1])
        ma200_val = close.rolling(200).mean().iloc[-1]
        ma200 = float(ma200_val) if pd.notna(ma200_val) else None
        week52_high, week52_low = _calc_52w_range(frame)
        day_change_dollar, day_change_pct = _calc_day_change(close, price)
        week_change_dollar, week_change_pct = _calc_week_change(close, price)
        month_change_dollar, month_change_pct = _calc_month_change(close, price)
        ytd_change_dollar, ytd_change_pct = calc_ytd_change(close)

        return_1m = _calc_return(close, TRADING_DAYS_1M)
        return_2m = _calc_return(close, TRADING_DAYS_2M)
        return_6m = _calc_return(close, TRADING_DAYS_6M)
        if return_1m is None or return_2m is None:
            return None

        avg_volume = float(volume.tail(20).mean()) if not volume.empty else 0.0

        return StockMetrics(
            ticker=ticker,
            name=name,
            sector=sector,
            price=price,
            day_change_dollar=day_change_dollar,
            day_change_pct=day_change_pct,
            week_change_dollar=week_change_dollar,
            week_change_pct=week_change_pct,
            month_change_dollar=month_change_dollar,
            month_change_pct=month_change_pct,
            ytd_change_dollar=ytd_change_dollar,
            ytd_change_pct=ytd_change_pct,
            return_1m=return_1m,
            return_2m=return_2m,
            return_6m=return_6m,
            week52_high=week52_high,
            week52_low=week52_low,
            ma20=ma20,
            ma50=ma50,
            ma60=ma60,
            ma200=ma200,
            avg_volume=avg_volume,
            above_ma20=price > ma20,
            above_ma50=price > ma50,
            above_ma60=price > ma60,
        )
    except Exception as exc:
        logger.debug("Metrics failed for %s: %s", ticker, exc)
        return None


def _passes_daily_filters(metrics: StockMetrics) -> bool:
    return (
        metrics.price >= MIN_PRICE
        and metrics.avg_volume >= MIN_AVG_VOLUME
        and metrics.return_1m > 0
        and metrics.return_2m > 0
        and metrics.above_ma20
        and metrics.above_ma50
    )


def _passes_momentum_filters(metrics: StockMetrics) -> bool:
    """Legacy daily: positive 1M/2M returns, above MA20 & MA60."""
    return (
        metrics.price >= MIN_PRICE
        and metrics.avg_volume >= MIN_AVG_VOLUME
        and metrics.return_1m > 0
        and metrics.return_2m > 0
        and metrics.above_ma20
        and metrics.above_ma60
    )


def _passes_weekly_filters(metrics: StockMetrics) -> bool:
    return (
        metrics.price >= MIN_PRICE
        and metrics.avg_volume >= MIN_AVG_VOLUME
        and metrics.week_change_pct is not None
        and metrics.week_change_pct > 0
    )


def _passes_monthly_filters(metrics: StockMetrics) -> bool:
    return (
        metrics.price >= MIN_PRICE
        and metrics.avg_volume >= MIN_AVG_VOLUME
        and metrics.month_change_pct is not None
        and metrics.month_change_pct > 0
    )


def _collect_stock_metrics(
    universe: pd.DataFrame,
    filter_fn,
    sort_key: str,
    top_n: int,
    history: dict | None = None,
) -> list[dict]:
    tickers = universe["Symbol"].tolist()
    meta = {
        row["Symbol"]: {
            "name": row.get("Security", ""),
            "sector": row.get("GICS Sector", ""),
        }
        for _, row in universe.iterrows()
    }

    if history is None:
        history = fetch_stock_history(tickers)
    qualified: list[StockMetrics] = []

    for ticker, frame in history.items():
        info = meta.get(ticker, {})
        metrics = _compute_metrics(
            ticker,
            frame,
            name=info.get("name", ""),
            sector=info.get("sector", ""),
        )
        if metrics and filter_fn(metrics):
            qualified.append(metrics)

    qualified.sort(key=lambda s: getattr(s, sort_key) or -999, reverse=True)
    return [asdict(s) for s in qualified[:top_n]]


def analyze_top_stocks(
    universe: pd.DataFrame, top_n: int = 20, history: dict | None = None
) -> list[dict]:
    """Daily: top S&P 500 stocks by day change; MA20/MA50 momentum filters."""
    return _collect_stock_metrics(
        universe, _passes_daily_filters, "day_change_pct", top_n, history=history
    )


def analyze_top_stocks_momentum(
    universe: pd.DataFrame, top_n: int = 20, history: dict | None = None
) -> list[dict]:
    """Legacy daily: top stocks by 1M return; positive 1M/2M, above MA20 & MA60."""
    return _collect_stock_metrics(
        universe, _passes_momentum_filters, "return_1m", top_n, history=history
    )


def analyze_top_stocks_weekly(
    universe: pd.DataFrame, top_n: int = 20, history: dict | None = None
) -> list[dict]:
    """Weekly: top S&P 500 stocks by 5-day return with positive week."""
    return _collect_stock_metrics(
        universe, _passes_weekly_filters, "week_change_pct", top_n, history=history
    )


def analyze_top_stocks_monthly(
    universe: pd.DataFrame, top_n: int = 20, history: dict | None = None
) -> list[dict]:
    """Monthly: top S&P 500 stocks by ~21-day (1M) return with positive month."""
    return _collect_stock_metrics(
        universe, _passes_monthly_filters, "month_change_pct", top_n, history=history
    )


def _analyze_ticker_list(
    tickers: dict[str, str],
    top_n: int,
    sort_key: str = "return_1m",
    history: dict | None = None,
) -> list[dict]:
    """Rank ETFs/funds by sort_key; includes all tickers in universe (no sector filtering)."""
    results: list[dict] = []
    if history is None:
        history = fetch_stock_history(list(tickers.keys()))

    for ticker in tickers:
        frame = history.get(ticker)
        if frame is None or frame.empty:
            continue
        try:
            metrics = _compute_metrics(
                ticker, frame, name=tickers.get(ticker, ticker), sector="Fund"
            )
            if metrics is None:
                continue
            results.append(asdict(metrics))
        except Exception as exc:
            logger.debug("Analysis skipped for %s: %s", ticker, exc)

    results.sort(key=lambda r: r.get(sort_key) or -999, reverse=True)
    return results[:top_n]


def analyze_top_etfs(top_n: int = 20, history: dict | None = None) -> list[dict]:
    return _analyze_ticker_list(
        {t: t for t in ETF_UNIVERSE}, top_n, sort_key="day_change_pct", history=history
    )


def analyze_top_etfs_momentum(top_n: int = 20, history: dict | None = None) -> list[dict]:
    return _analyze_ticker_list(
        {t: t for t in ETF_UNIVERSE}, top_n, sort_key="return_1m", history=history
    )


def analyze_top_etfs_weekly(top_n: int = 20, history: dict | None = None) -> list[dict]:
    return _analyze_ticker_list(
        {t: t for t in ETF_UNIVERSE}, top_n, sort_key="week_change_pct", history=history
    )


def analyze_top_etfs_monthly(top_n: int = 20, history: dict | None = None) -> list[dict]:
    return _analyze_ticker_list(
        {t: t for t in ETF_UNIVERSE}, top_n, sort_key="month_change_pct", history=history
    )


def analyze_top_mutual_funds(top_n: int = 20, history: dict | None = None) -> list[dict]:
    return _analyze_ticker_list(
        MUTUAL_FUND_UNIVERSE, top_n, sort_key="day_change_pct", history=history
    )


def analyze_top_mutual_funds_momentum(top_n: int = 20, history: dict | None = None) -> list[dict]:
    return _analyze_ticker_list(
        MUTUAL_FUND_UNIVERSE, top_n, sort_key="return_1m", history=history
    )


def analyze_top_mutual_funds_weekly(top_n: int = 20, history: dict | None = None) -> list[dict]:
    return _analyze_ticker_list(
        MUTUAL_FUND_UNIVERSE, top_n, sort_key="week_change_pct", history=history
    )


def analyze_top_mutual_funds_monthly(top_n: int = 20, history: dict | None = None) -> list[dict]:
    return _analyze_ticker_list(
        MUTUAL_FUND_UNIVERSE, top_n, sort_key="month_change_pct", history=history
    )
