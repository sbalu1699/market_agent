"""Tests for shared return helpers."""

from __future__ import annotations

import pandas as pd
import pytest

from mcp_server.tools.returns import calc_day_change, calc_return, calc_week_change


def test_calc_return_positive():
    close = pd.Series([100.0, 110.0], index=pd.date_range("2024-01-01", periods=2))
    assert calc_return(close, 1) == pytest.approx(10.0)


def test_calc_day_change():
    close = pd.Series([100.0, 110.0], index=pd.date_range("2024-01-01", periods=2))
    dollar, pct = calc_day_change(close)
    assert dollar == pytest.approx(10.0)
    assert pct == pytest.approx(10.0)


def test_calc_week_change_insufficient_data():
    close = pd.Series([100.0, 101.0], index=pd.date_range("2024-01-01", periods=2))
    dollar, pct = calc_week_change(close)
    assert dollar is None
    assert pct is None
