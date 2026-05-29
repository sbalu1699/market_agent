"""Yahoo Finance data fetcher for S&P 500 universe."""

from __future__ import annotations

import logging
from io import StringIO

import pandas as pd
import requests
import yfinance as yf

logger = logging.getLogger(__name__)

WIKI_SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
TRADING_DAYS_1M = 21
TRADING_DAYS_2M = 42
TRADING_DAYS_6M = 126
TRADING_DAYS_1W = 5
TRADING_DAYS_52W = 252
HISTORY_PERIOD = "1y"

_HEADERS = {
    "User-Agent": "MarketAgent/1.0 (daily market brief; contact: local)",
}


def _normalize_ticker(symbol: str) -> str:
    return symbol.replace(".", "-")


def fetch_sp500_universe() -> pd.DataFrame:
    """Fetch S&P 500 constituents and sector metadata from Wikipedia."""
    try:
        response = requests.get(WIKI_SP500_URL, headers=_HEADERS, timeout=30)
        response.raise_for_status()
        tables = pd.read_html(StringIO(response.text))
        df = tables[0].copy()
        df["Symbol"] = df["Symbol"].apply(_normalize_ticker)
        return df[["Symbol", "Security", "GICS Sector", "GICS Sub-Industry"]]
    except Exception as exc:
        logger.error("Failed to fetch S&P 500 universe: %s", exc)
        raise


def last_trading_date(history: dict[str, pd.DataFrame]) -> pd.Timestamp | None:
    """Latest closing date across downloaded price history."""
    latest: pd.Timestamp | None = None
    for frame in history.values():
        if frame.empty or not isinstance(frame.index, pd.DatetimeIndex):
            continue
        ts = pd.Timestamp(frame.index[-1])
        if latest is None or ts > latest:
            latest = ts
    return latest


def fetch_stock_history(
    tickers: list[str],
    period: str = HISTORY_PERIOD,
    batch_size: int = 50,
) -> dict[str, pd.DataFrame]:
    """Download OHLCV history for tickers in batches; skip failures gracefully."""
    results: dict[str, pd.DataFrame] = {}

    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        try:
            data = yf.download(
                batch,
                period=period,
                group_by="ticker",
                auto_adjust=True,
                threads=True,
                progress=False,
            )
        except Exception as exc:
            logger.warning("Batch download failed (%s): %s", batch[:3], exc)
            continue

        if len(batch) == 1:
            ticker = batch[0]
            if not data.empty:
                results[ticker] = _prepare_frame(data)
            continue

        for ticker in batch:
            try:
                if ticker not in data.columns.get_level_values(0):
                    continue
                frame = data[ticker].dropna(how="all")
                if not frame.empty:
                    results[ticker] = _prepare_frame(frame)
            except Exception as exc:
                logger.debug("Skipping %s: %s", ticker, exc)

    return results


def _prepare_frame(df: pd.DataFrame) -> pd.DataFrame:
    frame = df.copy()
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(0)
    frame.columns = [str(c).title() for c in frame.columns]
    if "Close" not in frame.columns:
        raise ValueError("Missing Close column")
    return frame.dropna(subset=["Close"])


def fetch_single_ticker(ticker: str, period: str = HISTORY_PERIOD) -> pd.DataFrame | None:
    """Fetch history for a single ticker with graceful failure."""
    try:
        data = yf.download(
            ticker,
            period=period,
            auto_adjust=True,
            progress=False,
        )
        if data.empty:
            return None
        return _prepare_frame(data)
    except Exception as exc:
        logger.debug("Failed to fetch %s: %s", ticker, exc)
        return None


def calc_ytd_change(close: pd.Series) -> tuple[float | None, float | None]:
    """Year-to-date dollar and percentage change from first trading day of the year."""
    if close.empty or len(close) < 2:
        return None, None

    price = float(close.iloc[-1])
    if not isinstance(close.index, pd.DatetimeIndex):
        return None, None

    last_date = close.index[-1]
    year_start = pd.Timestamp(year=last_date.year, month=1, day=1)
    if last_date.tzinfo is not None:
        year_start = year_start.tz_localize(last_date.tzinfo)

    ytd_prices = close[close.index >= year_start]
    if ytd_prices.empty:
        return None, None

    start = float(ytd_prices.iloc[0])
    if start == 0:
        return None, None

    return price - start, (price / start - 1) * 100
