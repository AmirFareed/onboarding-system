"""Centralized logging configuration.

Configures Python's built-in ``logging`` module once per process. Every
component in the application should obtain loggers through
``logging.getLogger(__name__)`` and must never use ``print``.

The configuration installs a console handler for development observability and
an optional rotating file handler for persistent audit trails. All handlers
share a common, machine-readable log format.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Final

#: Directory used for persistent log files.
DEFAULT_LOG_DIR: Final = "logs"
#: Base name of the rotating log file written by the file handler.
DEFAULT_LOG_FILE: Final = "backend.log"
#: Single-file size at which the log rotates to a new file.
_LOG_FILE_MAX_BYTES: Final = 5 * 1024 * 1024
#: Number of rotated log files kept on disk.
_LOG_FILE_BACKUP_COUNT: Final = 5

#: Shared format used by every handler.
_LOG_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)s | "
    "%(filename)s:%(lineno)d | %(message)s"
)

#: Loggers owned by third-party libraries that should echo the configured level
#: instead of their own noisy defaults.
_THIRD_PARTY_LOGGERS: Final = ("uvicorn", "uvicorn.access", "uvicorn.error", "sqlalchemy")

#: Track whether handlers were already installed to keep configuration idempotent.
_logger_configured = False


def _build_formatter() -> logging.Formatter:
    """Return the shared log formatter."""
    return logging.Formatter(_LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")


def _add_console_handler(logger: logging.Logger, formatter: logging.Formatter) -> None:
    """Attach a stream handler writing to standard output."""
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)


def _add_file_handler(
    logger: logging.Logger,
    formatter: logging.Formatter,
    log_dir: str,
    log_file: str,
) -> None:
    """Attach a rotating file handler, creating the log directory if needed."""
    log_path = Path(log_dir) / log_file
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=_LOG_FILE_MAX_BYTES,
        backupCount=_LOG_FILE_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)


def configure_logging(
    level: str = "INFO",
    *,
    log_dir: str = DEFAULT_LOG_DIR,
    log_file: str | None = DEFAULT_LOG_FILE,
) -> None:
    """Configure application-wide logging.

    Installs console and optional rotating file handlers on the root logger and
    aligns third-party loggers with the requested level. Calling this function
    multiple times is safe; handlers are installed only on the first call.

    Args:
        level: Root logging level (e.g. ``"INFO"``, ``"DEBUG"``).
        log_dir: Directory that stores the file log. Ignored when ``log_file``
            is ``None``.
        log_file: Name of the rotating log file, or ``None`` to disable file
            logging.
    """
    global _logger_configured
    if _logger_configured:
        return

    normalized_level = level.upper()
    root_logger = logging.getLogger()
    root_logger.setLevel(normalized_level)

    formatter = _build_formatter()
    _add_console_handler(root_logger, formatter)
    if log_file is not None:
        _add_file_handler(root_logger, formatter, log_dir, log_file)

    for name in _THIRD_PARTY_LOGGERS:
        logging.getLogger(name).setLevel(normalized_level)

    logging.getLogger(__name__).info("Logging configured at %s level", normalized_level)
    _logger_configured = True
