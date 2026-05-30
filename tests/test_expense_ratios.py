"""Tests for parallel expense-ratio fetching."""

from __future__ import annotations

from mcp_server.tools import market_data


def test_fetch_expense_ratios_fetches_missing_in_parallel(monkeypatch):
    calls: list[str] = []

    def mock_fetch(ticker: str) -> float | None:
        calls.append(ticker)
        return 0.12 if ticker == "SPY" else None

    monkeypatch.setattr(market_data, "fetch_expense_ratio", mock_fetch)
    market_data.clear_expense_ratio_cache()

    result = market_data.fetch_expense_ratios(["SPY", "QQQ", "IWM"], max_workers=3)

    assert set(calls) == {"SPY", "QQQ", "IWM"}
    assert result["SPY"] == 0.12
    assert result["QQQ"] is None


def test_fetch_expense_ratios_uses_cache(monkeypatch):
    calls: list[str] = []

    def mock_fetch(ticker: str) -> float | None:
        calls.append(ticker)
        return 0.25

    monkeypatch.setattr(market_data, "fetch_expense_ratio", mock_fetch)
    market_data.clear_expense_ratio_cache()

    first = market_data.fetch_expense_ratios(["SPY", "QQQ"], max_workers=2)
    second = market_data.fetch_expense_ratios(["SPY", "QQQ", "IWM"], max_workers=2)

    assert first["SPY"] == 0.25
    assert second["IWM"] == 0.25
    assert calls.count("SPY") == 1
    assert calls.count("QQQ") == 1
    assert calls.count("IWM") == 1


def test_expense_ratio_from_info_net_expense():
    info = {"netExpenseRatio": 0.09}
    assert market_data._expense_ratio_from_info(info) == 0.09
