"""MCP server exposing market analysis tools."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.fastmcp import FastMCP

from mcp_server.tools.analyzer import analyze_top_etfs, analyze_top_mutual_funds, analyze_top_stocks
from mcp_server.tools.emailer import send_report_email
from mcp_server.tools.market_data import fetch_sp500_universe
from mcp_server.tools.sectors import get_sector_breakdown

mcp = FastMCP("market-agent")


@mcp.tool()
def fetch_sp500() -> str:
    """Fetch the S&P 500 universe from Wikipedia with sector metadata."""
    df = fetch_sp500_universe()
    return df.to_json(orient="records")


@mcp.tool()
def get_top_stocks(top_n: int = 20) -> str:
    """
    Analyze S&P 500 and return top performers.
    Filters: price >= $2, avg volume >= 500k, positive 1m & 2m returns, above MA20 & MA50.
    """
    universe = fetch_sp500_universe()
    results = analyze_top_stocks(universe, top_n=top_n)
    return json.dumps(results, indent=2)


@mcp.tool()
def get_sector_performance() -> str:
    """Return average 1m and 2m returns broken down by GICS sector."""
    universe = fetch_sp500_universe()
    breakdown = get_sector_breakdown(universe)
    return json.dumps(breakdown, indent=2)


@mcp.tool()
def get_top_etfs(top_n: int = 20) -> str:
    """Return top-performing ETFs ranked by 1-month return."""
    results = analyze_top_etfs(top_n=top_n)
    return json.dumps(results, indent=2)


@mcp.tool()
def get_top_mutual_funds(top_n: int = 20) -> str:
    """Return top-performing mutual funds ranked by 1-month return."""
    results = analyze_top_mutual_funds(top_n=top_n)
    return json.dumps(results, indent=2)


@mcp.tool()
def send_email_report(
    stocks_json: str,
    sectors_json: str,
    etfs_json: str,
    mutual_funds_json: str = "[]",
    summary: str = "",
) -> str:
    """Send an HTML market report email via Resend."""
    stocks = json.loads(stocks_json)
    sectors = json.loads(sectors_json)
    etfs = json.loads(etfs_json)
    mutual_funds = json.loads(mutual_funds_json)
    result = send_report_email(stocks, sectors, etfs, mutual_funds, summary=summary)
    return json.dumps(result)


if __name__ == "__main__":
    mcp.run(transport="stdio")
