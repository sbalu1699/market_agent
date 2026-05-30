"""Scheduler — daily 11:30 AM & 7:04 PM ET, weekly Sat 10:06 AM ET, monthly last day 7:00 PM ET."""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from agent import (
    _combined_fund_expense_ratios,
    run_agent,
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
logger = logging.getLogger("scheduler")

ET = ZoneInfo("America/New_York")


def daily_job() -> None:
    """Daily report — runs on market days only (morning and evening slots)."""
    now = datetime.now(ET)
    if not is_trading_day(now):
        logger.info("Daily skipped — not a trading day (%s)", now.strftime("%A %Y-%m-%d"))
        return

    logger.info("Starting daily market report at %s ET", now.strftime("%H:%M"))
    mode = os.getenv("AGENT_MODE", "pipeline").lower()
    try:
        if mode == "agent":
            run_agent()
        else:
            run_pipeline()
        logger.info("Daily report completed.")
    except Exception:
        logger.exception("Daily report failed.")


def weekly_job() -> None:
    """Weekly report — every Saturday morning ET."""
    now = datetime.now(ET)
    logger.info("Starting weekly market report at %s ET", now.strftime("%H:%M"))
    try:
        expense_ratios = _combined_fund_expense_ratios()
        run_weekly_pipeline(expense_ratios=expense_ratios)
        run_bullion_weekly_pipeline(expense_ratios=expense_ratios)
        logger.info("Weekly report completed.")
    except Exception:
        logger.exception("Weekly report failed.")


def monthly_job() -> None:
    """Monthly report — last calendar day of each month, evening ET."""
    now = datetime.now(ET)
    logger.info("Starting monthly market report at %s ET", now.strftime("%H:%M"))
    try:
        expense_ratios = _combined_fund_expense_ratios()
        run_monthly_pipeline(expense_ratios=expense_ratios)
        run_bullion_monthly_pipeline(expense_ratios=expense_ratios)
        logger.info("Monthly report completed.")
    except Exception:
        logger.exception("Monthly report failed.")


def main() -> None:
    daily_am_hour = int(os.getenv("DAILY_AM_SCHEDULE_HOUR", "11"))
    daily_am_minute = int(os.getenv("DAILY_AM_SCHEDULE_MINUTE", "30"))
    daily_pm_hour = int(os.getenv("SCHEDULE_HOUR", "19"))
    daily_pm_minute = int(os.getenv("SCHEDULE_MINUTE", "4"))
    weekly_hour = int(os.getenv("WEEKLY_SCHEDULE_HOUR", "11"))
    weekly_minute = int(os.getenv("WEEKLY_SCHEDULE_MINUTE", "6"))
    monthly_hour = int(os.getenv("MONTHLY_SCHEDULE_HOUR", "19"))
    monthly_minute = int(os.getenv("MONTHLY_SCHEDULE_MINUTE", "0"))

    scheduler = BlockingScheduler()
    scheduler.add_job(
        daily_job,
        CronTrigger(hour=daily_am_hour, minute=daily_am_minute, timezone=ET),
        id="daily_market_report_am",
        name="Daily Market Report (AM)",
    )
    scheduler.add_job(
        daily_job,
        CronTrigger(hour=daily_pm_hour, minute=daily_pm_minute, timezone=ET),
        id="daily_market_report_pm",
        name="Daily Market Report (PM)",
    )
    scheduler.add_job(
        weekly_job,
        CronTrigger(day_of_week="sat", hour=weekly_hour, minute=weekly_minute, timezone=ET),
        id="weekly_market_report",
        name="Weekly Market Report",
    )
    scheduler.add_job(
        monthly_job,
        CronTrigger(day="last", hour=monthly_hour, minute=monthly_minute, timezone=ET),
        id="monthly_market_report",
        name="Monthly Market Report",
    )

    logger.info(
        "Scheduler started — daily %d:%02d AM & %d:%02d PM ET (trading days), "
        "weekly Sat %d:%02d AM ET, monthly last day %d:%02d PM ET",
        daily_am_hour,
        daily_am_minute,
        daily_pm_hour % 12 or 12,
        daily_pm_minute,
        weekly_hour,
        weekly_minute,
        monthly_hour % 12 or 12,
        monthly_minute,
    )
    scheduler.start()


if __name__ == "__main__":
    main()
