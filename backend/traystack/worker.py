"""Database-backed worker. No extraction runs inside the HTTP request lifecycle."""

import argparse
import logging
import signal
import threading
from datetime import UTC, datetime

from sqlalchemy import create_engine, update
from sqlalchemy.orm import sessionmaker

from traystack.config import Settings
from traystack.models import ProcessingJob
from traystack.services.processing import run_once
from traystack.services.storage import LocalStorage

logger = logging.getLogger(__name__)


def recover_running(sessions: sessionmaker) -> int:
    """Operator command: stop all workers first. A recovered run can never publish later."""
    with sessions.begin() as session:
        result = session.execute(
            update(ProcessingJob)
            .where(ProcessingJob.status == "running")
            .values(
                status="failed", error_message="worker_interrupted", finished_at=datetime.now(UTC)
            )
        )
        return result.rowcount


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Process at most one queued job")
    parser.add_argument(
        "--recover-running",
        action="store_true",
        help="Fail interrupted runs; stop all workers first",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = Settings()
    engine = create_engine(
        config.database_url, pool_pre_ping=True, connect_args={"connect_timeout": 5}
    )
    sessions = sessionmaker(engine, expire_on_commit=False)
    stopped = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    try:
        if args.recover_running:
            logger.info("Recovered %s interrupted runs", recover_running(sessions))
            return
        storage = LocalStorage(config.storage_path)
        while not stopped.is_set():
            try:
                worked = run_once(sessions, storage)
            except Exception as error:
                # Never print SQL parameters, source text or raw OCR error messages.
                logger.error("Worker operation failed: %s", type(error).__name__)
                worked = False
            if args.once:
                break
            if not worked:
                stopped.wait(config.worker_poll_seconds)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
