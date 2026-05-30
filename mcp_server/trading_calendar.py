"""NYSE trading calendar helpers."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pandas_market_calendars as mcal

ET = ZoneInfo("America/New_York")
_NYSE = mcal.get_calendar("NYSE")


def is_trading_day(dt: datetime | None = None) -> bool:
    """Return True if the given ET datetime falls on an NYSE session."""
    dt = dt or datetime.now(ET)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ET)
    else:
        dt = dt.astimezone(ET)
    day = pd.Timestamp(dt.date())
    valid = _NYSE.valid_days(start_date=day, end_date=day)
    return len(valid) > 0


def is_trading_date(day: date) -> bool:
    """Return True if the calendar date is an NYSE session."""
    ts = pd.Timestamp(day)
    valid = _NYSE.valid_days(start_date=ts, end_date=ts)
    return len(valid) > 0
