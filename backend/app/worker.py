"""Standalone worker process.

Single claim path: the dispatcher's worker loop atomically claims QUEUED jobs from the DB
(the durable source of truth), holds the lease with heartbeats, and writes a worker
heartbeat row used as the worker readiness signal. This module only starts and stops it.
"""

import asyncio
import logging
import signal

from backend.app.core.database import init_db
from backend.app.core.dispatcher import get_dispatcher

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("sentinel.worker")


async def run_worker() -> None:
    await init_db()
    dispatcher = get_dispatcher()
    dispatcher.start()
    logger.info("worker started id=%s max_concurrent=%s", dispatcher.worker_id, dispatcher.max_concurrent)

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
        await dispatcher.stop()
        logger.info("worker stopped id=%s", dispatcher.worker_id)


def main() -> None:
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
