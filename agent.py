"""Claude agent loop for daily market analysis."""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

# Project root on path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from mcp_server.tools.analyzer import (
    ETF_UNIVERSE,
    MUTUAL_FUND_UNIVERSE,
    analyze_top_etfs,
    analyze_top_etfs_monthly,
    analyze_top_etfs_momentum,
    analyze_top_etfs_weekly,
    analyze_top_mutual_funds,
    analyze_top_mutual_funds_monthly,
    analyze_top_mutual_funds_momentum,
    analyze_top_mutual_funds_weekly,
    analyze_top_stocks,
    analyze_top_stocks_monthly,
    analyze_top_stocks_momentum,
    analyze_top_stocks_weekly,
)
from mcp_server.tools.emailer import send_report_email
from mcp_server.tools.market_data import fetch_sp500_universe, fetch_stock_history
from mcp_server.tools.sectors import (
    get_sector_breakdown,
    get_sector_breakdown_monthly,
    get_sector_breakdown_momentum,
    get_sector_breakdown_weekly,
)

load_dotenv(ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("market-agent")

SYSTEM = """
You are a financial market analyst agent. Every trading day you:
1. Fetch the S&P 500 universe, filter out penny stocks
2. Analyze top performing stocks (positive 1m + 2m returns, above MA20/MA50)
3. Get sector performance breakdown
4. Identify top ETFs and mutual funds
5. Send a well-formatted email report

Be concise, data-driven, and highlight standout movers.
"""

TOOLS = [
    {
        "name": "fetch_sp500",
        "description": "Fetch S&P 500 constituents and sector metadata from Wikipedia.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_top_stocks",
        "description": (
            "Analyze S&P 500 stocks. Returns top performers with positive 1m & 2m returns, "
            "price >= $2, avg volume >= 500k, above MA20 & MA50."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"top_n": {"type": "integer", "default": 20}},
            "required": [],
        },
    },
    {
        "name": "get_sector_performance",
        "description": "Average 1m and 2m returns by GICS sector for S&P 500.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_top_etfs",
        "description": "Top ETFs ranked by period return (day/week/month matching report type).",
        "input_schema": {
            "type": "object",
            "properties": {"top_n": {"type": "integer", "default": 20}},
            "required": [],
        },
    },
    {
        "name": "get_top_mutual_funds",
        "description": "Top mutual funds ranked by period return (day/week/month matching report type).",
        "input_schema": {
            "type": "object",
            "properties": {"top_n": {"type": "integer", "default": 20}},
            "required": [],
        },
    },
    {
        "name": "send_email_report",
        "description": "Send HTML market report via Resend.",
        "input_schema": {
            "type": "object",
            "properties": {
                "stocks_json": {"type": "string"},
                "sectors_json": {"type": "string"},
                "etfs_json": {"type": "string"},
                "mutual_funds_json": {"type": "string"},
                "summary": {"type": "string"},
            },
            "required": ["stocks_json", "sectors_json", "etfs_json", "mutual_funds_json"],
        },
    },
]


def execute_tool(name: str, inputs: dict) -> str:
    """Dispatch tool calls to Python implementations."""
    try:
        if name == "fetch_sp500":
            df = fetch_sp500_universe()
            return df.to_json(orient="records")

        if name == "get_top_stocks":
            universe = fetch_sp500_universe()
            top_n = inputs.get("top_n", 20)
            return json.dumps(analyze_top_stocks(universe, top_n=top_n), indent=2)

        if name == "get_sector_performance":
            universe = fetch_sp500_universe()
            return json.dumps(get_sector_breakdown(universe), indent=2)

        if name == "get_top_etfs":
            top_n = inputs.get("top_n", 20)
            return json.dumps(analyze_top_etfs(top_n=top_n), indent=2)

        if name == "get_top_mutual_funds":
            top_n = inputs.get("top_n", 20)
            return json.dumps(analyze_top_mutual_funds(top_n=top_n), indent=2)

        if name == "send_email_report":
            result = send_report_email(
                stocks=json.loads(inputs["stocks_json"]),
                sectors=json.loads(inputs["sectors_json"]),
                etfs=json.loads(inputs["etfs_json"]),
                mutual_funds=json.loads(inputs.get("mutual_funds_json", "[]")),
                summary=inputs.get("summary", ""),
            )
            return json.dumps(result)

        return json.dumps({"error": f"Unknown tool: {name}"})
    except Exception as exc:
        logger.exception("Tool %s failed", name)
        return json.dumps({"error": str(exc)})


def run_agent(max_turns: int = 10) -> None:
    """Run the Claude agent loop until completion or max turns."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set in .env")

    client = Anthropic(api_key=api_key)
    messages: list[dict] = [
        {
            "role": "user",
            "content": (
                "Run today's market analysis. Fetch S&P 500 data, find top stocks, "
                "get sector breakdown, identify top ETFs and mutual funds, then send the email report. "
                "Write a 2-3 sentence summary highlighting standout movers for the email."
            ),
        }
    ]

    for turn in range(max_turns):
        logger.info("Agent turn %d/%d", turn + 1, max_turns)
        response = client.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
            max_tokens=4096,
            system=SYSTEM,
            tools=TOOLS,
            messages=messages,
        )

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            logger.info("Agent finished.")
            break

        if response.stop_reason != "tool_use":
            logger.warning("Unexpected stop reason: %s", response.stop_reason)
            break

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            logger.info("Executing tool: %s", block.name)
            output = execute_tool(block.name, block.input)
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": output,
                }
            )

        messages.append({"role": "user", "content": tool_results})
    else:
        logger.warning("Agent reached max turns without completing.")


def run_pipeline() -> dict:
    """
    Direct pipeline (no LLM) — sends two daily emails back-to-back:
    1. Day-change ranking (MA20/MA50 filters)
    2. Legacy momentum ranking by 1M return (MA20/MA60 filters)
    """
    logger.info("Running direct market pipeline (dual daily reports)...")
    universe = fetch_sp500_universe()
    stock_history = fetch_stock_history(universe["Symbol"].tolist())
    fund_tickers = list(dict.fromkeys([*ETF_UNIVERSE, *MUTUAL_FUND_UNIVERSE.keys()]))
    fund_history = fetch_stock_history(fund_tickers)

    # --- Report 1: day-change ranking (current) ---
    stocks = analyze_top_stocks(universe, top_n=20, history=stock_history)
    sectors = get_sector_breakdown(universe, history=stock_history)
    etfs = analyze_top_etfs(top_n=20, history=fund_history)
    mutual_funds = analyze_top_mutual_funds(top_n=20, history=fund_history)

    top_mover = stocks[0]["ticker"] if stocks else "N/A"
    best_sector = sectors[0]["sector"] if sectors else "N/A"
    top_etf = etfs[0]["ticker"] if etfs else "N/A"
    day_pct = stocks[0].get("day_change_pct") if stocks else None
    summary = (
        f"Top day mover: {top_mover}"
        f"{f' ({day_pct:+.2f}%)' if day_pct is not None else ''}. "
        f"Leading sector: {best_sector}. "
        f"Top ETF: {top_etf}. "
        f"{len(stocks)} stocks met all criteria."
    )

    email_day = send_report_email(
        stocks, sectors, etfs, mutual_funds, summary=summary, period="daily", variant="day"
    )
    logger.info("Daily (day-change) report sent.")

    # --- Report 2: legacy 1M momentum ranking ---
    stocks_mom = analyze_top_stocks_momentum(universe, top_n=20, history=stock_history)
    sectors_mom = get_sector_breakdown_momentum(universe, history=stock_history)
    etfs_mom = analyze_top_etfs_momentum(top_n=20, history=fund_history)
    mutual_mom = analyze_top_mutual_funds_momentum(top_n=20, history=fund_history)

    top_mom = stocks_mom[0]["ticker"] if stocks_mom else "N/A"
    best_sector_mom = sectors_mom[0]["sector"] if sectors_mom else "N/A"
    top_etf_mom = etfs_mom[0]["ticker"] if etfs_mom else "N/A"
    mom_pct = stocks_mom[0].get("return_1m") if stocks_mom else None
    summary_mom = (
        f"Top 1M mover: {top_mom}"
        f"{f' ({mom_pct:+.2f}%)' if mom_pct is not None else ''}. "
        f"Leading sector: {best_sector_mom}. "
        f"Top ETF: {top_etf_mom}. "
        f"{len(stocks_mom)} stocks met momentum criteria (MA20/MA60)."
    )

    email_momentum = send_report_email(
        stocks_mom,
        sectors_mom,
        etfs_mom,
        mutual_mom,
        summary=summary_mom,
        period="daily",
        variant="momentum",
    )
    logger.info("Daily (momentum) report sent.")

    return {
        "stocks": stocks,
        "sectors": sectors,
        "etfs": etfs,
        "mutual_funds": mutual_funds,
        "summary": summary,
        "email": email_day,
        "momentum": {
            "stocks": stocks_mom,
            "sectors": sectors_mom,
            "etfs": etfs_mom,
            "mutual_funds": mutual_mom,
            "summary": summary_mom,
            "email": email_momentum,
        },
    }


def run_weekly_pipeline() -> dict:
    """Weekly pipeline — best performers over the 5-day trading week."""
    logger.info("Running weekly market pipeline...")
    universe = fetch_sp500_universe()
    stocks = analyze_top_stocks_weekly(universe, top_n=20)
    sectors = get_sector_breakdown_weekly(universe)
    etfs = analyze_top_etfs_weekly(top_n=20)
    mutual_funds = analyze_top_mutual_funds_weekly(top_n=20)

    top_mover = stocks[0]["ticker"] if stocks else "N/A"
    best_sector = sectors[0]["sector"] if sectors else "N/A"
    top_etf = etfs[0]["ticker"] if etfs else "N/A"
    week_pct = stocks[0].get("week_change_pct") if stocks else None
    summary = (
        f"Weekly top mover: {top_mover}"
        f"{f' (+{week_pct:.2f}%)' if week_pct is not None else ''}. "
        f"Leading sector: {best_sector}. "
        f"Top ETF: {top_etf}."
    )

    email_result = send_report_email(
        stocks, sectors, etfs, mutual_funds, summary=summary, period="weekly"
    )
    return {
        "stocks": stocks,
        "sectors": sectors,
        "etfs": etfs,
        "mutual_funds": mutual_funds,
        "summary": summary,
        "email": email_result,
    }


def run_monthly_pipeline() -> dict:
    """Monthly pipeline — best performers over ~21 trading days (1 month)."""
    logger.info("Running monthly market pipeline...")
    universe = fetch_sp500_universe()
    stocks = analyze_top_stocks_monthly(universe, top_n=20)
    sectors = get_sector_breakdown_monthly(universe)
    etfs = analyze_top_etfs_monthly(top_n=20)
    mutual_funds = analyze_top_mutual_funds_monthly(top_n=20)

    top_mover = stocks[0]["ticker"] if stocks else "N/A"
    best_sector = sectors[0]["sector"] if sectors else "N/A"
    top_etf = etfs[0]["ticker"] if etfs else "N/A"
    month_pct = stocks[0].get("month_change_pct") if stocks else None
    summary = (
        f"Monthly top mover: {top_mover}"
        f"{f' (+{month_pct:.2f}%)' if month_pct is not None else ''}. "
        f"Leading sector: {best_sector}. "
        f"Top ETF: {top_etf}."
    )

    email_result = send_report_email(
        stocks, sectors, etfs, mutual_funds, summary=summary, period="monthly"
    )
    return {
        "stocks": stocks,
        "sectors": sectors,
        "etfs": etfs,
        "mutual_funds": mutual_funds,
        "summary": summary,
        "email": email_result,
    }


if __name__ == "__main__":
    mode = os.getenv("AGENT_MODE", "agent").lower()
    report_type = os.getenv("REPORT_TYPE", "daily")
    if len(sys.argv) > 1:
        report_type = sys.argv[1].lower()

    if mode == "pipeline":
        if report_type == "weekly":
            result = run_weekly_pipeline()
        elif report_type == "monthly":
            result = run_monthly_pipeline()
        else:
            result = run_pipeline()
        print(json.dumps({
            "email": result["email"],
            "email_momentum": result.get("momentum", {}).get("email"),
            "stock_count": len(result["stocks"]),
            "stock_count_momentum": len(result.get("momentum", {}).get("stocks", [])),
            "etf_count": len(result["etfs"]),
            "mutual_fund_count": len(result["mutual_funds"]),
            "report_type": report_type,
        }, indent=2))
    else:
        run_agent()
