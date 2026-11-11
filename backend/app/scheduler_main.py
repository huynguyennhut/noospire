"""Standalone Scheduler Worker Entry Point.

Executes continuous cron schedule evaluations in Asia/Ho_Chi_Minh,
overrun coalescing, and periodic worker lease recovery.
"""

import asyncio
import logging
import signal
import sys

from backend.app.core.database import init_db
from backend.app.core.scheduler import get_scheduler_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("sentinel.scheduler_main")


async def run_scheduler() -> None:
    logger.info("Starting standalone scheduler process...")
    await init_db()

    scheduler_engine = get_scheduler_engine()
    scheduler_engine.start()

    stop_event = asyncio.Event()

    def handle_signal():
        logger.info("Received termination signal, stopping scheduler...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, handle_signal)
        except (NotImplementedError, RuntimeError):
            pass

    while not stop_event.is_set():
        try:
            await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            break

    await scheduler_engine.stop()
    logger.info("Standalone scheduler stopped.")


def main() -> None:
    asyncio.run(run_scheduler())


if __name__ == "__main__":
    main()
