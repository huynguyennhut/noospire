"""Standalone scheduler process (compose service `scheduler`).

Runs the Milestone 4 monitor scheduler: atomic (schedule, slot) claims, single coalesced
catch-up, lease reaper, dead letters and stale-source notifications.

The legacy DailySchedule engine (`backend.app.core.scheduler`) is NOT started: it launched
legacy "all"-engine scans outside the defensive execution flow.
"""

import asyncio
import logging
import signal

from backend.app.core.database import init_db
from backend.app.core.monitor_scheduler import get_monitor_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("noospire.scheduler_main")


async def run_scheduler() -> None:
    await init_db()
    sched = get_monitor_scheduler()
    sched.start()
    logger.info("monitor scheduler started id=%s tick=%ss", sched.scheduler_id, sched.interval_seconds)

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except (NotImplementedError, RuntimeError):
            pass  # Windows: rely on process termination / KeyboardInterrupt
    try:
        await stop_event.wait()
    finally:
        await sched.stop()
        logger.info("monitor scheduler stopped id=%s", sched.scheduler_id)


def main() -> None:
    try:
        asyncio.run(run_scheduler())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
