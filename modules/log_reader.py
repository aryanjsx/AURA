"""
AURA — Log Reader

Reads the tail of log files so the user can quickly inspect recent
activity without leaving the CLI.
"""

from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import List

from command_engine.logger import get_logger

logger = get_logger("aura.log_reader")


def read_last_lines(file_path: str, lines: int = 20) -> List[str]:
    """Return the last *lines* lines of a text file.

    Parameters
    ----------
    file_path:
        Path to the log (or any text) file.
    lines:
        Number of trailing lines to return.

    Returns
    -------
    list[str]
        The requested lines (without trailing newlines).
    """
    target = Path(file_path).resolve()

    if not target.is_file():
        msg = f"File not found: {target}"
        logger.warning(msg)
        return [msg]

    try:
        with target.open("r", encoding="utf-8", errors="replace") as fh:
            tail = deque(fh, maxlen=lines)
        result = [line.rstrip("\n") for line in tail]
        logger.info("Read last %d lines from %s", lines, target)
        return result
    except OSError as exc:
        logger.error("Error reading %s: %s", target, exc)
        return [f"Error reading file: {exc}"]
