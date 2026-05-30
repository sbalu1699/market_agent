"""Tests for NYSE trading-day detection."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from mcp_server.trading_calendar import is_trading_day

ET = ZoneInfo("America/New_York")


def test_saturday_not_trading_day():
    sat = datetime(2026, 5, 30, 12, 0, tzinfo=ET)
    assert not is_trading_day(sat)


def test_new_years_day_not_trading_day():
    holiday = datetime(2026, 1, 1, 12, 0, tzinfo=ET)
    assert not is_trading_day(holiday)


def test_regular_weekday_is_trading_day():
    wed = datetime(2026, 5, 27, 12, 0, tzinfo=ET)
    assert is_trading_day(wed)
