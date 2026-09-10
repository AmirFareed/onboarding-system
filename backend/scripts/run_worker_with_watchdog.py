"""Run the bulk queue worker under a crash-restarting supervisor.

The worker can hit a real, intermittent native access-violation crash inside
PaddleOCR's inference engine (documented in CONTEXT.md, 2026-08-23/24) --
confirmed to sometimes take down the whole worker process, not just the job
it was working on. The underlying cause lives in paddle/paddlex's compiled
internals and isn't something this project can safely patch. This script
doesn't fix that: it just makes a crash survivable, by restarting the worker
automatically instead of leaving bulk uploads silently stuck forever with no
worker to process them.

Usage (same working directory/venv as running the worker directly)::

    .venv/Scripts/python.exe scripts/run_worker_with_watchdog.py [--workers N]

Any arguments are passed straight through to ``app.bulk_queue``. A clean
shutdown (SIGTERM/SIGINT, or the worker exiting with status 0 on its own)
stops the supervisor too -- it only restarts on a crash (nonzero exit).
"""

from __future__ import annotations

import subprocess
import sys
import time
from datetime import UTC, datetime

#: Minimum seconds between restarts, so a worker that crashes instantly on
#: every attempt (e.g. a genuinely broken environment, not a transient OCR
#: crash) doesn't spin the CPU in a tight restart loop.
_MIN_RESTART_DELAY_SECONDS = 5.0

#: If the worker crashes more often than this many times within
#: _RAPID_CRASH_WINDOW_SECONDS, stop restarting -- something is structurally
#: broken (not the intermittent OCR crash this watchdog exists for), and
#: keeping the demo pipeline flapping is worse than a single terminal failure.
_MAX_RAPID_CRASHES = 5
_RAPID_CRASH_WINDOW_SECONDS = 120.0


def _log(message: str) -> None:
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    print(f"{timestamp} | watchdog | {message}", flush=True)


def main() -> int:
    args = sys.argv[1:]
    command = [sys.executable, "-m", "app.bulk_queue", *args]
    recent_crash_times: list[float] = []

    _log(f"Starting worker under watchdog: {' '.join(command)}")
    while True:
        started_at = time.monotonic()
        process = subprocess.run(command)
        elapsed = time.monotonic() - started_at

        if process.returncode == 0:
            _log("Worker exited cleanly (status 0); watchdog stopping too.")
            return 0

        _log(
            f"Worker exited with status {process.returncode} after "
            f"{elapsed:.1f}s -- restarting."
        )

        now = time.monotonic()
        recent_crash_times = [
            t for t in recent_crash_times if now - t < _RAPID_CRASH_WINDOW_SECONDS
        ]
        recent_crash_times.append(now)
        if len(recent_crash_times) > _MAX_RAPID_CRASHES:
            _log(
                f"{len(recent_crash_times)} crashes within "
                f"{_RAPID_CRASH_WINDOW_SECONDS:.0f}s -- this looks like a "
                "persistent failure, not the known intermittent OCR crash. "
                "Stopping the watchdog rather than restart-looping forever."
            )
            return 1

        time.sleep(_MIN_RESTART_DELAY_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
