#!/usr/bin/env python3
"""APScheduler worker: runs the channel monitor on a configurable interval."""

import asyncio
import logging
import os
import sys
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.data_retention import delete_old_leads
from scripts.monitor_channels import run_sync_cycle

log = logging.getLogger("worker")

SYNC_INTERVAL_HOURS = float(os.getenv("SYNC_INTERVAL_HOURS", "4"))


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        run_sync_cycle,
        trigger=IntervalTrigger(hours=SYNC_INTERVAL_HOURS),
        id="channel_sync",
        name="Channel monitor sync",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=300,
    )
    scheduler.add_job(
        delete_old_leads,
        trigger=CronTrigger(hour=3, minute=0),
        id="delete_old_leads",
        name="Data retention: delete old leads",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=3600,
    )
    return scheduler


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log.info("Channel monitor worker starting (interval=%.1fh)", SYNC_INTERVAL_HOURS)

    scheduler = build_scheduler()
    scheduler.start()

    # Run immediately on startup, then on schedule
    await run_sync_cycle()

    try:
        while True:
            await asyncio.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        log.info("Shutdown requested")
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    asyncio.run(main())
