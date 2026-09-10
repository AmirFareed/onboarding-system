"""Run dedicated bulk queue worker processes.

Production deployments that want queue draining fully outside the HTTP request
lifecycle start one or more of these processes (one per host, or more when a
single worker's concurrency cap is enough):

    .venv/bin/python -m app.bulk_queue --workers 2

Workers poll the PostgreSQL queue forever, claim jobs atomically (``FOR UPDATE
SKIP LOCKED``), heartbeat their in-flight job so slow documents are not
declared stale, and recover jobs abandoned by crashed workers after the
configured timeout. SIGTERM/SIGINT triggers a graceful shutdown after the
currently claimed job completes.

Each configured worker runs as its own OS **process**, not a thread in a
shared process (see :func:`app.bulk_queue.workers.run_worker_process`'s
docstring for the full reasoning: PaddleOCR's process-wide predictor lock
means N worker threads in one process still only OCR one document at a
time, regardless of ``--workers``; separate processes each get their own
independent predictor). The actual per-process entry point lives in
``workers.py``, not here -- a function defined in a script executed as
``__main__`` can't be pickled/resolved by a ``multiprocessing`` "spawn"
child, which needs to import its target by a normal dotted path.

Uses ``spawn`` explicitly, on every platform (not the POSIX default
``fork``): a spawned worker is a genuinely fresh interpreter that never
inherits the parent's already-open database connections, which is also the
only start method Windows supports -- this keeps local Windows development
and POSIX production identical instead of behaving differently by platform.

Shutdown is coordinated through a ``multiprocessing.Event``, not by
forwarding the OS signal to each child: Windows cannot deliver a real
SIGTERM to another process in a way Python can intercept, so
signal-forwarding would silently do nothing there. A shared ``Event`` works
identically everywhere: this process's own signal handler sets it, and each
worker process's watcher thread (see ``run_worker_process``) reacts to it.
"""

from __future__ import annotations

import argparse
import logging
import multiprocessing as mp
import signal

from app.bulk_queue.workers import run_worker_process
from app.core.config import get_settings
from app.core.logging import configure_logging

logger = logging.getLogger(__name__)


def main() -> int:
    """Run the configured worker count, each as its own process, until shutdown."""
    parser = argparse.ArgumentParser(
        description="Run dedicated bulk queue worker processes against PostgreSQL.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Number of worker OS processes to run (default: bulk_queue_workers setting).",
    )
    args = parser.parse_args()

    settings = get_settings()
    configure_logging(level=settings.log_level)
    worker_count = args.workers or settings.bulk_queue_workers

    ctx = mp.get_context("spawn")
    shutdown_event = ctx.Event()
    processes = [
        ctx.Process(
            target=run_worker_process,
            args=(i, shutdown_event),
            name=f"bulk-worker-{i}",
        )
        for i in range(worker_count)
    ]

    def _shutdown(_signum: int, _frame: object) -> None:
        logger.info(
            "Shutdown signal received; stopping %s bulk queue worker process(es) gracefully",
            len(processes),
        )
        shutdown_event.set()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    logger.info("Starting %s bulk queue worker process(es)", len(processes))
    for process in processes:
        process.start()
    for process in processes:
        process.join()
    logger.info("All bulk queue worker processes stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
