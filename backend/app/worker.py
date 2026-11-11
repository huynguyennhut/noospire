"""Standalone Scanner Worker Entry Point.

Executes continuous database queue polling, worker lease heartbeats,
engine adapter invocations, and idempotent result persistence.
"""

import asyncio
import logging
import os
import signal
import sys
import uuid

from backend.app.core.database import AsyncSessionLocal, init_db
from backend.app.core.dispatcher import get_dispatcher
from backend.app.core.queue import IDBDurableQueue

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("sentinel.worker")


async def run_worker() -> None:
    worker_id = f"worker-{os.getpid()}-{uuid.uuid4().hex[:6]}"
    logger.info("Starting standalone scanner worker: %s", worker_id)
    await init_db()

    dispatcher = get_dispatcher()
    dispatcher.start()

    stop_event = asyncio.Event()

    def handle_signal():
        logger.info("Received termination signal, shutting down worker...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, handle_signal)
        except (NotImplementedError, RuntimeError):
            pass

    while not stop_event.is_set():
        try:
            async with AsyncSessionLocal() as session:
                scan = await IDBDurableQueue.claim_next_job(session, worker_id, lease_duration_seconds=60)
                if scan:
                    logger.info("Worker %s claimed scan %s (attempt %s, fencing_token %s)", worker_id, scan.id, scan.attempts, scan.fencing_token)
                    await dispatcher.dispatch_scan(scan.id)
                else:
                    await asyncio.sleep(1.0)
        except Exception as e:
            logger.error("Error in worker polling loop: %s", e, exc_info=True)
            await asyncio.sleep(2.0)

    await dispatcher.stop()
    logger.info("Standalone scanner worker %s stopped.", worker_id)


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
