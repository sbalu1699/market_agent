"""Resend HTML email delivery for market reports."""

from __future__ import annotations

import logging
import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

import resend

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")
CST = ZoneInfo("America/Chicago")


def _to_et(dt: datetime | date) -> datetime:
    if isinstance(dt, date) and not isinstance(dt, datetime):
        dt = datetime(dt.year, dt.month, dt.day)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=ET)
    return dt.astimezone(ET)


def _format_report_date(as_of: datetime | date | None, period: str = "daily") -> str:
    """Human-readable market data date for report headers."""
    dt = _to_et(as_of or datetime.now(ET))
    if period == "weekly":
        return f"Week Ending {dt.strftime('%B %d, %Y')}"
    if period == "monthly":
        return dt.strftime("%B %Y")
    return dt.strftime("%B %d, %Y")


def _format_sent_timestamp(sent_at: datetime | None, period: str = "daily") -> str:
    tz = CST if period in ("weekly", "monthly") else ET
    label = "CST" if period in ("weekly", "monthly") else "ET"
    now = sent_at or datetime.now(tz)
    if now.tzinfo is None:
        now = now.replace(tzinfo=tz)
    else:
        now = now.astimezone(tz)
    return now.strftime(f"%A, %B %d, %Y %I:%M %p {label}")


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


def _fmt_forex_rate(ticker: str, value: float | None) -> str:
    if value is None:
        return "N/A"
    if ticker == "USDINR=X":
        return f"₹{value:.2f}"
    if ticker in ("USDJPY=X", "USDCAD=X"):
        return f"{value:.3f}"
    return f"{value:.4f}"


def _fmt_forex_change(abs_change: float | None, pct: float | None) -> str:
    if abs_change is None and pct is None:
        return "N/A"
    if abs_change is None:
        return _fmt_pct(pct)
    sign = "+" if abs_change >= 0 else "-"
    abs_part = f"{sign}{abs(abs_change):.4f}"
    if pct is None:
        return abs_part
    return f"{abs_part} ({_fmt_pct(pct)})"


def _forex_primary_sort_cell(ticker: str, d_val: float | None, p_val: float | None) -> str:
    color = _color(p_val if p_val is not None else d_val)
    text = _fmt_forex_change(d_val, p_val)
    return f'<td style="color:{color};font-weight:600">{text}</td>'


def _build_forex_table(forex: list[dict], period: str = "weekly") -> str:
    if not forex:
        return "<p>No forex data available.</p>"

    chg_d, chg_p = _primary_sort_keys(period)
    sort_header = _primary_sort_header(period)
    rows = ""
    for rank, fx in enumerate(forex, start=1):
        d_val = fx.get(chg_d) if chg_d else None
        p_val = fx.get(chg_p) if chg_p else None
        ticker = fx["ticker"]
        rows += f"""
        <tr>
          <td>{rank}</td>
          <td><strong>{fx.get('name', ticker)}</strong></td>
          <td>{_fmt_forex_rate(ticker, fx.get('price'))}</td>
          {_forex_primary_sort_cell(ticker, d_val, p_val)}
          <td style="color:{_color(fx.get('ytd_change_pct'))}">{_fmt_pct(fx.get('ytd_change_pct'))}</td>
          <td style="color:{_color(fx.get('return_1m'))}">{_fmt_pct(fx.get('return_1m'))}</td>
          <td style="color:{_color(fx.get('return_2m'))}">{_fmt_pct(fx.get('return_2m'))}</td>
          <td style="color:{_color(fx.get('return_6m'))}">{_fmt_pct(fx.get('return_6m'))}</td>
        </tr>"""

    return f"""
    <table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse;width:100%;margin-top:8px">
      <thead style="background:#1e293b;color:#fff">
        <tr>
          <th>#</th><th>Pair</th><th>Rate</th>
          <th style="background:#334155">{sort_header}</th>
          <th>YTD (%)</th><th>1M Return</th><th>2M Return</th><th>6M Return</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>"""


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


def _build_crypto_section(
    overview: list[dict],
    crypto_etfs: list[dict],
    period: str,
    variant: str,
) -> str:
    sort_header = _primary_sort_header(period, variant)
    overview_rows = ""
    for rank, c in enumerate(overview, start=1):
        chg_d, chg_p = _primary_sort_keys(period, variant)
        d_val = c.get(chg_d) if chg_d else None
        p_val = c.get(chg_p) if chg_p else None
        overview_rows += f"""
        <tr>
          <td>{rank}</td>
          <td><strong>{c.get('name', c['ticker'])}</strong></td>
          <td>{c['ticker']}</td>
          <td>${c['price']:.2f}</td>
          {_primary_sort_cell(d_val, p_val)}
          <td style="color:{_color(c.get('ytd_change_pct'))}">{_fmt_pct(c.get('ytd_change_pct'))}</td>
        </tr>"""

    overview_table = ""
    if overview:
        overview_table = f"""
    <table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse;width:100%;margin-top:8px">
      <thead style="background:#1e293b;color:#fff">
        <tr>
          <th>#</th><th>Asset</th><th>ETF</th><th>Price</th>
          <th style="background:#334155">{sort_header}</th>
          <th>YTD (%)</th>
        </tr>
      </thead>
      <tbody>{overview_rows}</tbody>
    </table>"""

    etf_table = _build_fund_table(crypto_etfs, "crypto ETF", period, variant)
    if not crypto_etfs:
        etf_table = "<p>No crypto ETF data available.</p>"

    return f"""
      <h2 style="margin-top:32px">Bitcoin &amp; Crypto</h2>
      <p style="font-size:13px;color:#64748b">
        Bitcoin and Ethereum via spot ETFs (IBIT, ETHA). Crypto ETF universe ranked by period return (full universe, top 20).
      </p>
      {overview_table}
      <h3 style="margin-top:20px;font-size:16px">Top Crypto ETFs</h3>
      {etf_table}"""


def build_html_report(
    stocks: list[dict],
    sectors: list[dict],
    etfs: list[dict],
    mutual_funds: list[dict],
    summary: str = "",
    period: str = "daily",
    variant: str = "day",
    as_of: datetime | date | None = None,
    crypto_overview: list[dict] | None = None,
    crypto_etfs: list[dict] | None = None,
) -> str:
    """Build a formatted HTML email body (daily, weekly, or monthly)."""
    report_date = _format_report_date(as_of, period)
    sent_at = _format_sent_timestamp(datetime.now(), period)
    as_of_line = (
        f'<p style="color:#64748b">Data as of {report_date} · Sent {sent_at}</p>'
    )

    if period == "weekly":
        title = f"Weekly Market Performance — {report_date}"
        subtitle = (
            "Top 20 ranked by 5-day week change. "
            "Stocks: positive week + liquidity filters. ETFs/funds: full universe."
        )
    elif period == "monthly":
        title = f"Monthly Market Performance — {report_date}"
        subtitle = (
            "Top 20 ranked by ~21-day month change. "
            "Stocks: positive month + liquidity filters. ETFs/funds: full universe."
        )
    elif variant == "momentum":
        title = f"Daily Market Performance — {report_date} (Momentum)"
        subtitle = (
            "Top 20 ranked by 1-month return. Stock filters: price ≥ $2, avg volume ≥ 500k, "
            "positive 1M & 2M returns, above MA20 & MA60. ETFs/funds: full universe."
        )
    else:
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
      {as_of_line}
      {f'<p><em>{summary}</em></p>' if summary else ''}

      <h2>Top Performing Stocks</h2>
      <p style="font-size:13px;color:#64748b">{subtitle}</p>
      {_build_stocks_table(stocks, period, variant)}

      <h2 style="margin-top:32px">Sector Breakdown</h2>
      {_build_sector_table(sectors, period, variant)}

      <h2 style="margin-top:32px">Top ETFs</h2>
      <p style="font-size:13px;color:#64748b">Top 20 ETFs ranked from the ETF universe only (sectors, semiconductors, international, thematic)</p>
      {_build_fund_table(etfs, "ETF", period, variant)}

      <h2 style="margin-top:32px">Top Mutual Funds</h2>
      <p style="font-size:13px;color:#64748b">Top 20 mutual funds ranked from the mutual fund universe only (index and sector-diverse funds)</p>
      {_build_fund_table(mutual_funds, "mutual fund", period, variant)}

      {_build_crypto_section(crypto_overview or [], crypto_etfs or [], period, variant)}

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
    as_of: datetime | date | None = None,
    crypto_overview: list[dict] | None = None,
    crypto_etfs: list[dict] | None = None,
) -> dict:
    """Send the market report via Resend."""
    api_key = os.getenv("RESEND_API_KEY")
    from_email = os.getenv("EMAIL_FROM")
    to_email = os.getenv("EMAIL_TO")

    if not all([api_key, from_email, to_email]):
        raise ValueError("Missing RESEND_API_KEY, EMAIL_FROM, or EMAIL_TO in environment")

    if subject is None:
        as_of_dt = _to_et(as_of or datetime.now(ET))
        date_str = as_of_dt.strftime("%Y-%m-%d")
        subjects = {
            "weekly": f"Market performance — Weekly ({date_str})",
            "monthly": f"Market performance — Monthly ({as_of_dt.strftime('%Y-%m')})",
            "daily": f"Market performance — {date_str}",
            "daily_momentum": f"Market performance — {date_str} (Momentum)",
        }
        key = "daily_momentum" if period == "daily" and variant == "momentum" else period
        subject = subjects.get(key, "Market performance")

    html = build_html_report(
        stocks, sectors, etfs, mutual_funds or [], summary,
        period=period, variant=variant, as_of=as_of,
        crypto_overview=crypto_overview,
        crypto_etfs=crypto_etfs,
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


def build_bullion_html_report(
    market_overview: list[dict],
    stocks: list[dict],
    etfs: list[dict],
    mutual_funds: list[dict],
    summary: str = "",
    period: str = "weekly",
    as_of: datetime | date | None = None,
    forex_overview: list[dict] | None = None,
) -> str:
    """HTML report for bullion / precious metals (weekly or monthly)."""
    report_date = _format_report_date(as_of, period)
    sent_at = _format_sent_timestamp(datetime.now(), period)
    as_of_line = (
        f'<p style="color:#64748b">Data as of {report_date} · Sent {sent_at}</p>'
    )

    if period == "monthly":
        title = f"Bullion Market — Monthly ({report_date})"
        filter_desc = (
            "Top 20 ranked by ~21-day month change. "
            "Same stock rules: price ≥ $2, avg volume ≥ 500k, positive month return."
        )
    else:
        title = f"Bullion Market — Weekly ({report_date})"
        filter_desc = (
            "Top 20 ranked by 5-day week change. "
            "Same stock rules: price ≥ $2, avg volume ≥ 500k, positive week return."
        )

    overview_rows = ""
    for rank, m in enumerate(market_overview, start=1):
        chg_d, chg_p = _primary_sort_keys(period)
        d_val = m.get(chg_d) if chg_d else None
        p_val = m.get(chg_p) if chg_p else None
        overview_rows += f"""
        <tr>
          <td>{rank}</td>
          <td><strong>{m.get('name', m['ticker'])}</strong></td>
          <td>{m['ticker']}</td>
          <td>${m['price']:.2f}</td>
          {_primary_sort_cell(d_val, p_val)}
          <td style="color:{_color(m.get('ytd_change_pct'))}">{_fmt_pct(m.get('ytd_change_pct'))}</td>
          <td style="color:{_color(m.get('return_1m'))}">{_fmt_pct(m.get('return_1m'))}</td>
          <td style="color:{_color(m.get('return_2m'))}">{_fmt_pct(m.get('return_2m'))}</td>
          <td style="color:{_color(m.get('return_6m'))}">{_fmt_pct(m.get('return_6m'))}</td>
        </tr>"""

    sort_header = _primary_sort_header(period)
    overview_table = f"""
    <table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse;width:100%">
      <thead style="background:#1e293b;color:#fff">
        <tr>
          <th>#</th><th>Metal</th><th>ETF</th><th>Price</th>
          <th style="background:#334155">{sort_header}</th>
          <th>YTD (%)</th><th>1M Return</th><th>2M Return</th><th>6M Return</th>
        </tr>
      </thead>
      <tbody>{overview_rows}</tbody>
    </table>"""

    return f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family:Arial,sans-serif;color:#1e293b;max-width:900px;margin:auto">
      <h1 style="color:#0f172a">{title}</h1>
      {as_of_line}
      {f'<p><em>{summary}</em></p>' if summary else ''}

      <h2>Precious Metals Overview</h2>
      <p style="font-size:13px;color:#64748b">
        Gold, silver, platinum, and palladium via physical bullion ETFs (GLD, SLV, PPLT, PALL)
      </p>
      {overview_table}

      <h2 style="margin-top:32px">Major Forex</h2>
      <p style="font-size:13px;color:#64748b">
        USD/INR and other major currency pairs — spot rates via Yahoo Finance
      </p>
      {_build_forex_table(forex_overview or [], period)}

      <h2 style="margin-top:32px">Top Bullion Stocks</h2>
      <p style="font-size:13px;color:#64748b">{filter_desc}</p>
      {_build_stocks_table(stocks, period)}

      <h2 style="margin-top:32px">Top Bullion ETFs</h2>
      <p style="font-size:13px;color:#64748b">{filter_desc}</p>
      {_build_fund_table(etfs, "bullion ETF", period)}

      <h2 style="margin-top:32px">Top Bullion Mutual Funds</h2>
      <p style="font-size:13px;color:#64748b">Top 20 from bullion mutual fund universe; price ≥ $2 and positive period return (volume not applied — unavailable for funds on yfinance)</p>
      {_build_fund_table(mutual_funds, "bullion mutual fund", period)}

      <p style="margin-top:32px;font-size:12px;color:#94a3b8">
        Data via yfinance. Bullion commodities: gold, silver, platinum, palladium. Not investment advice.
      </p>
    </body>
    </html>
    """


def send_bullion_report_email(
    market_overview: list[dict],
    stocks: list[dict],
    etfs: list[dict],
    mutual_funds: list[dict] | None = None,
    summary: str = "",
    subject: str | None = None,
    period: str = "weekly",
    as_of: datetime | date | None = None,
    forex_overview: list[dict] | None = None,
) -> dict:
    """Send bullion market report via Resend."""
    api_key = os.getenv("RESEND_API_KEY")
    from_email = os.getenv("EMAIL_FROM")
    to_email = os.getenv("EMAIL_TO")

    if not all([api_key, from_email, to_email]):
        raise ValueError("Missing RESEND_API_KEY, EMAIL_FROM, or EMAIL_TO in environment")

    if subject is None:
        as_of_dt = _to_et(as_of or datetime.now(ET))
        date_str = as_of_dt.strftime("%Y-%m-%d")
        if period == "monthly":
            subject = f"Bullion market — Monthly ({as_of_dt.strftime('%Y-%m')})"
        else:
            subject = f"Bullion market — Weekly ({date_str})"

    html = build_bullion_html_report(
        market_overview, stocks, etfs, mutual_funds or [],
        summary, period=period, as_of=as_of, forex_overview=forex_overview,
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
            "report": "bullion",
        }
    except Exception as exc:
        logger.error("Resend bullion delivery failed: %s", exc)
        raise
