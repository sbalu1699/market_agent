"""Sector performance breakdown for S&P 500 constituents."""

from __future__ import annotations

import logging
from collections import defaultdict

import pandas as pd

from .market_data import TRADING_DAYS_1M, TRADING_DAYS_1W, calc_ytd_change, fetch_stock_history

logger = logging.getLogger(__name__)


def _calc_return(close: pd.Series, days: int) -> float | None:
    if len(close) < days + 1:
        return None
    start = close.iloc[-days - 1]
    end = close.iloc[-1]
    if start == 0:
        return None
    return float((end / start - 1) * 100)


def _calc_day_change(close: pd.Series) -> tuple[float | None, float | None]:
    if len(close) < 2:
        return None, None
    price = float(close.iloc[-1])
    prev = float(close.iloc[-2])
    if prev == 0:
        return None, None
    return price - prev, (price / prev - 1) * 100


def _calc_week_change(close: pd.Series) -> tuple[float | None, float | None]:
    if len(close) < TRADING_DAYS_1W + 1:
        return None, None
    price = float(close.iloc[-1])
    prev = float(close.iloc[-TRADING_DAYS_1W - 1])
    if prev == 0:
        return None, None
    pct = _calc_return(close, TRADING_DAYS_1W)
    return price - prev, pct


def _calc_month_change(close: pd.Series) -> tuple[float | None, float | None]:
    if len(close) < TRADING_DAYS_1M + 1:
        return None, None
    price = float(close.iloc[-1])
    prev = float(close.iloc[-TRADING_DAYS_1M - 1])
    if prev == 0:
        return None, None
    pct = _calc_return(close, TRADING_DAYS_1M)
    return price - prev, pct


def _aggregate_sectors(
    universe: pd.DataFrame,
    period: str,
    sort_key: str | None = None,
    history: dict | None = None,
) -> list[dict]:
    tickers = universe["Symbol"].tolist()
    sector_map = dict(zip(universe["Symbol"], universe["GICS Sector"]))
    if history is None:
        history = fetch_stock_history(tickers)

    sector_counts: dict[str, int] = defaultdict(int)
    sector_1m: dict[str, list[float]] = defaultdict(list)
    sector_2m: dict[str, list[float]] = defaultdict(list)
    sector_day_dollar: dict[str, list[float]] = defaultdict(list)
    sector_day_pct: dict[str, list[float]] = defaultdict(list)
    sector_week_dollar: dict[str, list[float]] = defaultdict(list)
    sector_week_pct: dict[str, list[float]] = defaultdict(list)
    sector_month_dollar: dict[str, list[float]] = defaultdict(list)
    sector_month_pct: dict[str, list[float]] = defaultdict(list)
    sector_ytd_dollar: dict[str, list[float]] = defaultdict(list)
    sector_ytd_pct: dict[str, list[float]] = defaultdict(list)

    for ticker, frame in history.items():
        try:
            sector = sector_map.get(ticker, "Unknown")
            close = frame["Close"]
            sector_counts[sector] += 1

            r1 = _calc_return(close, TRADING_DAYS_1M)
            r2 = _calc_return(close, 42)
            if r1 is not None:
                sector_1m[sector].append(r1)
            if r2 is not None:
                sector_2m[sector].append(r2)

            day_d, day_p = _calc_day_change(close)
            week_d, week_p = _calc_week_change(close)
            if day_d is not None:
                sector_day_dollar[sector].append(day_d)
            if day_p is not None:
                sector_day_pct[sector].append(day_p)
            if week_d is not None:
                sector_week_dollar[sector].append(week_d)
            if week_p is not None:
                sector_week_pct[sector].append(week_p)
            month_d, month_p = _calc_month_change(close)
            if month_d is not None:
                sector_month_dollar[sector].append(month_d)
            if month_p is not None:
                sector_month_pct[sector].append(month_p)
            ytd_d, ytd_p = calc_ytd_change(close)
            if ytd_d is not None:
                sector_ytd_dollar[sector].append(ytd_d)
            if ytd_p is not None:
                sector_ytd_pct[sector].append(ytd_p)
        except Exception as exc:
            logger.debug("Sector calc skipped for %s: %s", ticker, exc)

    def _avg(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 2) if values else None

    breakdown: list[dict] = []
    for sector in sorted(sector_counts.keys()):
        entry: dict = {
            "sector": sector,
            "stock_count": sector_counts[sector],
            "avg_return_1m": _avg(sector_1m.get(sector, [])),
            "avg_return_2m": _avg(sector_2m.get(sector, [])),
            "avg_ytd_change_dollar": _avg(sector_ytd_dollar.get(sector, [])),
            "avg_ytd_change_pct": _avg(sector_ytd_pct.get(sector, [])),
        }
        if period == "daily":
            entry["avg_day_change_dollar"] = _avg(sector_day_dollar.get(sector, []))
            entry["avg_day_change_pct"] = _avg(sector_day_pct.get(sector, []))
        elif period == "weekly":
            entry["avg_week_change_dollar"] = _avg(sector_week_dollar.get(sector, []))
            entry["avg_week_change_pct"] = _avg(sector_week_pct.get(sector, []))
        else:
            entry["avg_month_change_dollar"] = _avg(sector_month_dollar.get(sector, []))
            entry["avg_month_change_pct"] = _avg(sector_month_pct.get(sector, []))

        breakdown.append(entry)

    sort_keys = {
        "daily": "avg_day_change_pct",
        "weekly": "avg_week_change_pct",
        "monthly": "avg_month_change_pct",
    }
    key = sort_key or sort_keys[period]
    breakdown.sort(key=lambda x: x.get(key) or -999, reverse=True)
    return breakdown


def get_sector_breakdown(
    universe: pd.DataFrame, history: dict | None = None
) -> list[dict]:
    """Daily sector breakdown with day-change averages."""
    return _aggregate_sectors(universe, period="daily", history=history)


def get_sector_breakdown_momentum(
    universe: pd.DataFrame, history: dict | None = None
) -> list[dict]:
    """Legacy daily: sectors ranked by average 1M return."""
    return _aggregate_sectors(
        universe, period="daily", sort_key="avg_return_1m", history=history
    )


def get_sector_breakdown_weekly(universe: pd.DataFrame) -> list[dict]:
    """Weekly sector breakdown with 5-day change averages."""
    return _aggregate_sectors(universe, period="weekly")


def get_sector_breakdown_monthly(universe: pd.DataFrame) -> list[dict]:
    """Monthly sector breakdown with ~21-day change averages."""
    return _aggregate_sectors(universe, period="monthly")
