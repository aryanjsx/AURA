"""
AURA — Centralized Logging System

Provides a pre-configured logger that writes structured entries
(timestamp, command, status, errors) to a log file and, optionally,
to the console.  Settings are loaded from ``config.yaml``.

Usage from any module::

    from command_engine.logger import get_logger
    logger = get_logger()
    logger.info("File created: test.txt")
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from core.config_loader import get as get_config

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_LEVEL_MAP: dict[str, int] = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


def _ensure_log_dir(log_file: Path) -> None:
    """Create the log directory if it doesn't exist yet."""
    log_file.parent.mkdir(parents=True, exist_ok=True)


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

    log_rel = get_config("logging.file", "logs/aura.log")
    log_file = _PROJECT_ROOT / log_rel
    level_name = get_config("logging.level", "INFO")
    max_bytes = get_config("logging.max_bytes", 5_242_880)
    backup_count = get_config("logging.backup_count", 3)

    log_level = _LEVEL_MAP.get(str(level_name).upper(), logging.INFO)

    logger.setLevel(logging.DEBUG)

    _ensure_log_dir(log_file)

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger
