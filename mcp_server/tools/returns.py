"""Shared price return and period-change helpers."""

from __future__ import annotations

import pandas as pd

from .market_data import TRADING_DAYS_1M, TRADING_DAYS_1W


def calc_return(close: pd.Series, days: int) -> float | None:
    if len(close) < days + 1:
        return None
    start = close.iloc[-days - 1]
    end = close.iloc[-1]
    if start == 0:
        return None
    return float((end / start - 1) * 100)


def calc_day_change(
    close: pd.Series, price: float | None = None
) -> tuple[float | None, float | None]:
    if len(close) < 2:
        return None, None
    price = float(price if price is not None else close.iloc[-1])
    prev = float(close.iloc[-2])
    if prev == 0:
        return None, None
    dollar = price - prev
    pct = (price / prev - 1) * 100
    return dollar, pct


def calc_week_change(
    close: pd.Series, price: float | None = None
) -> tuple[float | None, float | None]:
    if len(close) < TRADING_DAYS_1W + 1:
        return None, None
    price = float(price if price is not None else close.iloc[-1])
    prev = float(close.iloc[-TRADING_DAYS_1W - 1])
    if prev == 0:
        return None, None
    dollar = price - prev
    pct = calc_return(close, TRADING_DAYS_1W)
    return dollar, pct


def calc_month_change(
    close: pd.Series, price: float | None = None
) -> tuple[float | None, float | None]:
    if len(close) < TRADING_DAYS_1M + 1:
        return None, None
    price = float(price if price is not None else close.iloc[-1])
    prev = float(close.iloc[-TRADING_DAYS_1M - 1])
    if prev == 0:
        return None, None
    dollar = price - prev
    pct = calc_return(close, TRADING_DAYS_1M)
    return dollar, pct
