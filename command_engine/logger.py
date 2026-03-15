"""
AURA — Centralized Logging System

Provides a pre-configured logger that writes structured entries
(timestamp, command, status, errors) to ``logs/aura.log`` and,
optionally, to the console.

Usage from any module::

    from command_engine.logger import get_logger
    logger = get_logger()
    logger.info("File created: test.txt")
"""

from __future__ import annotations

import logging
from pathlib import Path

_LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
_LOG_FILE = _LOG_DIR / "aura.log"

_LOG_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
)
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def _ensure_log_dir() -> None:
    """Create the log directory if it doesn't exist yet."""
    _LOG_DIR.mkdir(parents=True, exist_ok=True)


def get_logger(name: str = "aura") -> logging.Logger:
    """Return a logger configured with file and console handlers.

    Parameters
    ----------
    name:
        Logger name; defaults to ``"aura"``.

    Returns
    -------
    logging.Logger
        Ready-to-use logger instance.
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    _ensure_log_dir()

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    file_handler = logging.FileHandler(_LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger
