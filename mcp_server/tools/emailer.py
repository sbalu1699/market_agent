"""Resend HTML email delivery for market reports."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import resend

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")
CST = ZoneInfo("America/Chicago")


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "N/A"
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f}%"


def _fmt_price(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"${value:.2f}"


def _fmt_dollar_change(value: float | None) -> str:
    if value is None:
        return "N/A"
    sign = "+" if value >= 0 else "-"
    return f"{sign}${abs(value):.2f}"


PERIOD_COLUMNS = {
    "daily": ("day_change_dollar", "day_change_pct", "Day Chg ($)", "Day Chg (%)"),
    "weekly": ("week_change_dollar", "week_change_pct", "Week Chg ($)", "Week Chg (%)"),
    "monthly": ("month_change_dollar", "month_change_pct", "Month Chg ($)", "Month Chg (%)"),
}

SECTOR_COLUMNS = {
    "daily": ("avg_day_change_dollar", "avg_day_change_pct", "Avg Day ($)", "Avg Day (%)"),
    "weekly": ("avg_week_change_dollar", "avg_week_change_pct", "Avg Week ($)", "Avg Week (%)"),
    "monthly": ("avg_month_change_dollar", "avg_month_change_pct", "Avg Month ($)", "Avg Month (%)"),
}


PRIMARY_SORT_HEADERS = {
    "daily": "Primary Sort (Day)",
    "weekly": "Primary Sort (Week)",
    "monthly": "Primary Sort (Month)",
}


def _period_cols(period: str) -> tuple[str, str, str, str]:
    return PERIOD_COLUMNS.get(period, PERIOD_COLUMNS["daily"])


def _primary_sort_header(period: str, variant: str = "day") -> str:
    if period == "daily" and variant == "momentum":
        return "Primary Sort (1M)"
    return PRIMARY_SORT_HEADERS.get(period, PRIMARY_SORT_HEADERS["daily"])


def _primary_sort_keys(period: str, variant: str = "day") -> tuple[str | None, str | None]:
    if period == "daily" and variant == "momentum":
        return "month_change_dollar", "return_1m"
    chg_d, chg_p, _, _ = _period_cols(period)
    return chg_d, chg_p


def _sector_primary_sort_keys(period: str, variant: str = "day") -> tuple[str | None, str | None]:
    if period == "daily" and variant == "momentum":
        return None, "avg_return_1m"
    d_key, p_key, _, _ = SECTOR_COLUMNS.get(period, SECTOR_COLUMNS["daily"])
    return d_key, p_key


def _fmt_primary_sort(d_val: float | None, p_val: float | None) -> str:
    """Combined $ and % for the report period — primary ranking metric."""
    if d_val is None and p_val is None:
        return "N/A"
    if d_val is None:
        return _fmt_pct(p_val)
    return f"{_fmt_dollar_change(d_val)} ({_fmt_pct(p_val)})"


def _primary_sort_cell(d_val: float | None, p_val: float | None) -> str:
    color = _color(p_val if p_val is not None else d_val)
    return f'<td style="color:{color};font-weight:600">{_fmt_primary_sort(d_val, p_val)}</td>'


def _color(value: float | None) -> str:
    if value is None:
        return "#64748b"
    return "#16a34a" if value >= 0 else "#dc2626"


def _build_stocks_table(stocks: list[dict], period: str = "daily", variant: str = "day") -> str:
    if not stocks:
        return "<p>No stocks met all criteria.</p>"

    chg_d, chg_p = _primary_sort_keys(period, variant)
    sort_header = _primary_sort_header(period, variant)
    ma_label = "MA60" if variant == "momentum" else "MA50"
    ma_key = "ma60" if variant == "momentum" else "ma50"

    rows = ""
    for rank, s in enumerate(stocks, start=1):
        d_val = s.get(chg_d) if chg_d else None
        p_val = s.get(chg_p) if chg_p else None
        rows += f"""
        <tr>
          <td>{rank}</td>
          <td><strong>{s['ticker']}</strong></td>
          <td>{s.get('name', '')[:40]}</td>
          <td>{s.get('sector', '')}</td>
          <td>${s['price']:.2f}</td>
          {_primary_sort_cell(d_val, p_val)}
          <td style="color:{_color(s.get('ytd_change_dollar'))}">{_fmt_dollar_change(s.get('ytd_change_dollar'))}</td>
          <td style="color:{_color(s.get('ytd_change_pct'))}">{_fmt_pct(s.get('ytd_change_pct'))}</td>
          <td style="color:{_color(s['return_1m'])}">{_fmt_pct(s['return_1m'])}</td>
          <td style="color:{_color(s['return_2m'])}">{_fmt_pct(s['return_2m'])}</td>
          <td>{_fmt_price(s.get('week52_high'))}</td>
          <td>{_fmt_price(s.get('week52_low'))}</td>
          <td>${s['ma20']:.2f}</td>
          <td>${s[ma_key]:.2f}</td>
        </tr>"""

    return f"""
    <table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse;width:100%">
      <thead style="background:#1e293b;color:#fff">
        <tr>
          <th>#</th><th>Ticker</th><th>Name</th><th>Sector</th><th>Price</th>
          <th style="background:#334155">{sort_header}</th>
          <th>YTD ($)</th><th>YTD (%)</th>
          <th>1M Return</th><th>2M Return</th><th>52W High</th><th>52W Low</th>
          <th>MA20</th><th>{ma_label}</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>"""


def _build_sector_table(sectors: list[dict], period: str = "daily", variant: str = "day") -> str:
    d_key, p_key = _sector_primary_sort_keys(period, variant)
    sort_header = _primary_sort_header(period, variant)
    rows = ""
    for rank, s in enumerate(sectors, start=1):
        d_val = s.get(d_key) if d_key else None
        p_val = s.get(p_key) if p_key else None
        rows += f"""
        <tr>
          <td>{rank}</td>
          <td><strong>{s['sector']}</strong></td>
          <td>{s['stock_count']}</td>
          {_primary_sort_cell(d_val, p_val)}
          <td style="color:{_color(s.get('avg_ytd_change_dollar'))}">{_fmt_dollar_change(s.get('avg_ytd_change_dollar'))}</td>
          <td style="color:{_color(s.get('avg_ytd_change_pct'))}">{_fmt_pct(s.get('avg_ytd_change_pct'))}</td>
          <td style="color:{_color(s.get('avg_return_1m'))}">{_fmt_pct(s.get('avg_return_1m'))}</td>
          <td style="color:{_color(s.get('avg_return_2m'))}">{_fmt_pct(s.get('avg_return_2m'))}</td>
        </tr>"""

    headers = (
        f"<th>#</th><th>Sector</th><th>Stocks</th>"
        f'<th style="background:#334155">{sort_header}</th>'
        f"<th>Avg YTD ($)</th><th>Avg YTD (%)</th><th>Avg 1M</th><th>Avg 2M</th>"
    )

    return f"""
    <table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse;width:100%">
      <thead style="background:#1e293b;color:#fff">
        <tr>{headers}</tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>"""


def _build_fund_table(
    funds: list[dict], label: str, period: str = "daily", variant: str = "day"
) -> str:
    if not funds:
        return f"<p>No {label} data available.</p>"

    chg_d, chg_p = _primary_sort_keys(period, variant)
    sort_header = _primary_sort_header(period, variant)

    rows = ""
    for rank, f in enumerate(funds, start=1):
        d_val = f.get(chg_d) if chg_d else None
        p_val = f.get(chg_p) if chg_p else None
        rows += f"""
        <tr>
          <td>{rank}</td>
          <td><strong>{f['ticker']}</strong></td>
          <td>{f.get('name', f['ticker'])[:45]}</td>
          <td>${f['price']:.2f}</td>
          {_primary_sort_cell(d_val, p_val)}
          <td style="color:{_color(f.get('ytd_change_dollar'))}">{_fmt_dollar_change(f.get('ytd_change_dollar'))}</td>
          <td style="color:{_color(f.get('ytd_change_pct'))}">{_fmt_pct(f.get('ytd_change_pct'))}</td>
          <td style="color:{_color(f['return_1m'])}">{_fmt_pct(f['return_1m'])}</td>
          <td style="color:{_color(f['return_2m'])}">{_fmt_pct(f['return_2m'])}</td>
          <td>{_fmt_price(f.get('week52_high'))}</td>
          <td>{_fmt_price(f.get('week52_low'))}</td>
        </tr>"""

    return f"""
    <table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse;width:100%">
      <thead style="background:#1e293b;color:#fff">
        <tr>
          <th>#</th><th>Ticker</th><th>Name</th><th>Price</th>
          <th style="background:#334155">{sort_header}</th>
          <th>YTD ($)</th><th>YTD (%)</th>
          <th>1M Return</th><th>2M Return</th><th>52W High</th><th>52W Low</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>"""


def build_html_report(
    stocks: list[dict],
    sectors: list[dict],
    etfs: list[dict],
    mutual_funds: list[dict],
    summary: str = "",
    period: str = "daily",
    variant: str = "day",
) -> str:
    """Build a formatted HTML email body (daily, weekly, or monthly)."""
    if period == "weekly":
        now = datetime.now(CST).strftime("%A, %B %d, %Y %I:%M %p CST")
        title = "Weekly Market Performance"
        subtitle = (
            "Top 20 ranked by 5-day week change. "
            "Stocks: positive week + liquidity filters. ETFs/funds: full universe."
        )
    elif period == "monthly":
        now = datetime.now(CST).strftime("%A, %B %d, %Y %I:%M %p CST")
        title = "Monthly Market Performance"
        subtitle = (
            "Top 20 ranked by ~21-day month change. "
            "Stocks: positive month + liquidity filters. ETFs/funds: full universe."
        )
    elif variant == "momentum":
        report_date = datetime.now(ET).strftime("%B %d, %Y")
        now = datetime.now(ET).strftime("%A, %B %d, %Y %I:%M %p ET")
        title = f"Daily Market Performance — {report_date} (Momentum)"
        subtitle = (
            "Top 20 ranked by 1-month return. Stock filters: price ≥ $2, avg volume ≥ 500k, "
            "positive 1M & 2M returns, above MA20 & MA60. ETFs/funds: full universe."
        )
    else:
        report_date = datetime.now(ET).strftime("%B %d, %Y")
        now = datetime.now(ET).strftime("%A, %B %d, %Y %I:%M %p ET")
        title = f"Daily Market Performance — {report_date}"
        subtitle = (
            "Top 20 ranked by day change. Stock filters: price ≥ $2, avg volume ≥ 500k, "
            "positive 1M & 2M returns, above MA20 & MA50. ETFs/funds: full universe."
        )

    return f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family:Arial,sans-serif;color:#1e293b;max-width:900px;margin:auto">
      <h1 style="color:#0f172a">{title}</h1>
      <p style="color:#64748b">{now}</p>
      {f'<p><em>{summary}</em></p>' if summary else ''}

      <h2>Top Performing Stocks</h2>
      <p style="font-size:13px;color:#64748b">{subtitle}</p>
      {_build_stocks_table(stocks, period, variant)}

      <h2 style="margin-top:32px">Sector Breakdown</h2>
      {_build_sector_table(sectors, period, variant)}

      <h2 style="margin-top:32px">Top ETFs</h2>
      <p style="font-size:13px;color:#64748b">Top 20 ranked from broad-market ETF universe (all sectors, semiconductors, international, thematic)</p>
      {_build_fund_table(etfs, "ETF", period, variant)}

      <h2 style="margin-top:32px">Top Mutual Funds</h2>
      <p style="font-size:13px;color:#64748b">Sector-diverse mutual fund universe</p>
      {_build_fund_table(mutual_funds, "mutual fund", period, variant)}

      <p style="margin-top:32px;font-size:12px;color:#94a3b8">
        Data via yfinance &amp; Wikipedia. Not investment advice.
      </p>
    </body>
    </html>
    """


def send_report_email(
    stocks: list[dict],
    sectors: list[dict],
    etfs: list[dict],
    mutual_funds: list[dict] | None = None,
    summary: str = "",
    subject: str | None = None,
    period: str = "daily",
    variant: str = "day",
) -> dict:
    """Send the market report via Resend."""
    api_key = os.getenv("RESEND_API_KEY")
    from_email = os.getenv("EMAIL_FROM")
    to_email = os.getenv("EMAIL_TO")

    if not all([api_key, from_email, to_email]):
        raise ValueError("Missing RESEND_API_KEY, EMAIL_FROM, or EMAIL_TO in environment")

    if subject is None:
        today = datetime.now(ET).strftime("%Y-%m-%d")
        subjects = {
            "weekly": "Market performance — Weekly",
            "monthly": "Market performance — Monthly",
            "daily": f"Market performance — {today}",
            "daily_momentum": f"Market performance — {today} (Momentum)",
        }
        key = "daily_momentum" if period == "daily" and variant == "momentum" else period
        subject = subjects.get(key, "Market performance")

    html = build_html_report(
        stocks, sectors, etfs, mutual_funds or [], summary, period=period, variant=variant
    )

    resend.api_key = api_key

    try:
        response = resend.Emails.send(
            {
                "from": from_email,
                "to": [to_email],
                "subject": subject,
                "html": html,
            }
        )
        return {
            "status": "sent",
            "id": response.get("id") if isinstance(response, dict) else getattr(response, "id", None),
            "to": to_email,
            "period": period,
            "variant": variant,
        }
    except Exception as exc:
        logger.error("Resend delivery failed: %s", exc)
        raise
