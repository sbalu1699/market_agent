"""Scheduler — daily 7:04 PM ET + weekly Saturday 10:06 AM CST."""

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

from agent import run_agent, run_monthly_pipeline, run_pipeline, run_weekly_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("scheduler")

ET = ZoneInfo("America/New_York")
CST = ZoneInfo("America/Chicago")

US_MARKET_HOLIDAYS_2026 = {
    "2026-01-01",
    "2026-01-19",
    "2026-02-16",
    "2026-04-03",
    "2026-05-25",
    "2026-07-03",
    "2026-09-07",
    "2026-11-26",
    "2026-12-25",
}


def is_trading_day(dt: datetime | None = None) -> bool:
    """Return True if the given ET datetime is a weekday and not a market holiday."""
    dt = dt or datetime.now(ET)
    if dt.weekday() >= 5:
        return False
    return dt.strftime("%Y-%m-%d") not in US_MARKET_HOLIDAYS_2026


def daily_job() -> None:
    """Daily report — runs on market days only."""
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
    """Weekly report — runs every Saturday morning."""
    now = datetime.now(CST)
    logger.info("Starting weekly market report at %s CST", now.strftime("%H:%M"))
    try:
        run_weekly_pipeline()
        logger.info("Weekly report completed.")
    except Exception:
        logger.exception("Weekly report failed.")


def monthly_job() -> None:
    """Monthly report — runs on the 1st of each month."""
    now = datetime.now(CST)
    logger.info("Starting monthly market report at %s CST", now.strftime("%H:%M"))
    try:
        run_monthly_pipeline()
        logger.info("Monthly report completed.")
    except Exception:
        logger.exception("Monthly report failed.")


def main() -> None:
    daily_hour = int(os.getenv("SCHEDULE_HOUR", "19"))
    daily_minute = int(os.getenv("SCHEDULE_MINUTE", "4"))
    weekly_hour = int(os.getenv("WEEKLY_SCHEDULE_HOUR", "10"))
    weekly_minute = int(os.getenv("WEEKLY_SCHEDULE_MINUTE", "6"))
    monthly_hour = int(os.getenv("MONTHLY_SCHEDULE_HOUR", "10"))
    monthly_minute = int(os.getenv("MONTHLY_SCHEDULE_MINUTE", "6"))

    scheduler = BlockingScheduler()
    scheduler.add_job(
        daily_job,
        CronTrigger(hour=daily_hour, minute=daily_minute, timezone=ET),
        id="daily_market_report",
        name="Daily Market Report",
    )
    scheduler.add_job(
        weekly_job,
        CronTrigger(day_of_week="sat", hour=weekly_hour, minute=weekly_minute, timezone=CST),
        id="weekly_market_report",
        name="Weekly Market Report",
    )
    scheduler.add_job(
        monthly_job,
        CronTrigger(day=1, hour=monthly_hour, minute=monthly_minute, timezone=CST),
        id="monthly_market_report",
        name="Monthly Market Report",
    )

    logger.info(
        "Scheduler started — daily %d:%02d %s ET (trading days), "
        "weekly Sat %d:%02d AM CST, monthly 1st %d:%02d AM CST",
        daily_hour % 12 or 12,
        daily_minute,
        "PM" if daily_hour >= 12 else "AM",
        weekly_hour,
        weekly_minute,
        monthly_hour,
        monthly_minute,
    )
    scheduler.start()


if __name__ == "__main__":
    main()
