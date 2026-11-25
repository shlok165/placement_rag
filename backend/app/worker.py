"""Worker process: runs queued tasks and the nightly schedule."""

import logging
import signal
import threading
import time
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import get_sessionmaker
from app.embeddings import warm_up
from app.ingest import queue
from app.ingest.tasks import process_one, schedule_nightly

logger = logging.getLogger("app.worker")
HEARTBEAT = Path("/tmp/worker-heartbeat")
SCHEDULE_EVERY_S = 60


def main() -> None:
    configure_logging()
    stop = threading.Event()
    for name in (signal.SIGTERM, signal.SIGINT):
        signal.signal(name, lambda *_: stop.set())
    warm_up()
    sessions = get_sessionmaker()
    with sessions() as db:
        # Catch up on anything that passed its deadline while the worker was down.
        queue.enqueue(db, "expire")
        db.commit()
    logger.info("worker ready")
    next_schedule = 0.0
    while not stop.is_set():
        HEARTBEAT.touch()
        try:
            with sessions() as db:
                if time.monotonic() >= next_schedule:
                    schedule_nightly(db)
                    next_schedule = time.monotonic() + SCHEDULE_EVERY_S
                busy = process_one(db)
        except Exception as exc:
            logger.error("worker loop error", exc_info=exc)
            busy = False
        if not busy:
            stop.wait(get_settings().worker_poll_seconds)
    logger.info("worker stopped")


if __name__ == "__main__":
    main()
