#!/usr/bin/env python3
"""GitHub Actions entrypoint — run market pipelines when ET schedule matches."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from calendar import monthrange
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from agent import (
    _combined_fund_expense_ratios,
    run_bullion_monthly_pipeline,
    run_bullion_weekly_pipeline,
    run_monthly_pipeline,
    run_pipeline,
    run_weekly_pipeline,
)
from mcp_server.trading_calendar import is_trading_day

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("scheduled-run")

ET = ZoneInfo("America/New_York")
TOLERANCE_MINUTES = int(os.getenv("SCHEDULE_TOLERANCE_MINUTES", "20"))


def _slot_config(slot: str) -> dict:
    defaults = {
        "daily-am": {
            "hour": int(os.getenv("DAILY_AM_SCHEDULE_HOUR", "11")),
            "minute": int(os.getenv("DAILY_AM_SCHEDULE_MINUTE", "30")),
        },
        "daily-pm": {
            "hour": int(os.getenv("SCHEDULE_HOUR", "19")),
            "minute": int(os.getenv("SCHEDULE_MINUTE", "4")),
        },
        "weekly": {
            "hour": int(os.getenv("WEEKLY_SCHEDULE_HOUR", "11")),
            "minute": int(os.getenv("WEEKLY_SCHEDULE_MINUTE", "6")),
        },
        "monthly": {
            "hour": int(os.getenv("MONTHLY_SCHEDULE_HOUR", "19")),
            "minute": int(os.getenv("MONTHLY_SCHEDULE_MINUTE", "0")),
        },
    }
    if slot not in defaults:
        raise ValueError(f"Unknown slot: {slot}")
    return defaults[slot]


def _is_last_day_of_month(dt: datetime) -> bool:
    last = monthrange(dt.year, dt.month)[1]
    return dt.day == last


def _in_time_window(now: datetime, hour: int, minute: int) -> bool:
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    delta = abs((now - target).total_seconds())
    return delta <= TOLERANCE_MINUTES * 60


def resolve_schedule_slot(now: datetime | None = None) -> str:
    """Pick report slot from ET calendar (for GitHub cron, which often runs late)."""
    now = now or datetime.now(ET)
    if now.tzinfo is None:
        now = now.replace(tzinfo=ET)
    else:
        now = now.astimezone(ET)

    if _is_last_day_of_month(now) and now.hour >= 17:
        return "monthly"
    if now.weekday() == 5:
        return "weekly"
    if now.weekday() < 5:
        return "daily-pm" if now.hour >= 15 else "daily-am"
    return "unknown"


def should_run(
    slot: str,
    now: datetime | None = None,
    force: bool = False,
    trust_schedule: bool = False,
) -> bool:
    """Return True when this schedule slot should run."""
    if force:
        return True

    now = now or datetime.now(ET)
    if now.tzinfo is None:
        now = now.replace(tzinfo=ET)
    else:
        now = now.astimezone(ET)

    if not trust_schedule:
        cfg = _slot_config(slot)
        if not _in_time_window(now, cfg["hour"], cfg["minute"]):
            logger.info(
                "Skip %s — outside ET window (%02d:%02d ±%dm, now %s)",
                slot,
                cfg["hour"],
                cfg["minute"],
                TOLERANCE_MINUTES,
                now.strftime("%H:%M %Z"),
            )
            return False

    if slot in ("daily-am", "daily-pm"):
        if not is_trading_day(now):
            logger.info("Skip %s — not a trading day", slot)
            return False
    elif slot == "weekly":
        if now.weekday() != 5:
            logger.info("Skip weekly — not Saturday in ET")
            return False
    elif slot == "monthly":
        if not _is_last_day_of_month(now):
            logger.info("Skip monthly — not last calendar day in ET")
            return False

    return True


def run_slot(
    slot: str,
    force: bool = False,
    trust_schedule: bool = False,
) -> dict:
    now = datetime.now(ET)
    if not should_run(slot, now=now, force=force, trust_schedule=trust_schedule):
        return {"status": "skipped", "slot": slot}

    os.environ.setdefault("AGENT_MODE", "pipeline")
    logger.info("Running slot %s at %s ET", slot, now.strftime("%Y-%m-%d %H:%M"))

    if slot in ("daily-am", "daily-pm"):
        result = run_pipeline()
    elif slot == "weekly":
        expense_ratios = _combined_fund_expense_ratios()
        result = run_weekly_pipeline(expense_ratios=expense_ratios)
        bullion = run_bullion_weekly_pipeline(expense_ratios=expense_ratios)
        result = {"broad": result, "bullion": bullion}
    elif slot == "monthly":
        expense_ratios = _combined_fund_expense_ratios()
        result = run_monthly_pipeline(expense_ratios=expense_ratios)
        bullion = run_bullion_monthly_pipeline(expense_ratios=expense_ratios)
        result = {"broad": result, "bullion": bullion}
    else:
        raise ValueError(f"Unknown slot: {slot}")

    return {"status": "ok", "slot": slot, "result": result}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run market agent on ET schedule")
    parser.add_argument(
        "slot",
        choices=["daily-am", "daily-pm", "weekly", "monthly"],
        help="Schedule slot to evaluate",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Run even if ET time/day gates would skip",
    )
    parser.add_argument(
        "--trust-schedule",
        action="store_true",
        help="Skip exact-time check (use day/calendar gates only; for GitHub cron)",
    )
    args = parser.parse_args()
    output = run_slot(args.slot, force=args.force, trust_schedule=args.trust_schedule)
    print(json.dumps(output, indent=2, default=str))
    if output.get("status") == "skipped":
        if os.getenv("GITHUB_ACTIONS"):
            sys.exit(1)
        sys.exit(0)


if __name__ == "__main__":
    main()
