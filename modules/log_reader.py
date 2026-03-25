"""
AURA — Log Reader

Reads the tail of log files so the user can quickly inspect recent
activity without leaving the CLI.  Paths are resolved through
:func:`~command_engine.path_utils.resolve_path` so ``~`` and
smart-location keywords are handled transparently.
"""

from __future__ import annotations

from collections import deque

from command_engine.logger import get_logger
from command_engine.path_utils import resolve_path
from core.result import CommandResult

logger = get_logger("aura.log_reader")


def read_last_lines(file_path: str, lines: int = 20) -> CommandResult:
    """Return the last *lines* lines of a text file.

    Parameters
    ----------
    file_path:
        Path to the log (or any text) file — may contain ``~`` or
        smart-location keywords.
    lines:
        Number of trailing lines to return.

    Returns
    -------
    CommandResult
        ``data["lines"]`` contains the list of text lines.
    """
    try:
        target = resolve_path(file_path)
    except (ValueError, OSError) as exc:
        msg = f"Invalid path or permission denied: {exc}"
        logger.warning(msg)
        return CommandResult(success=False, message=msg, command_type="logs.show")

    if not target.is_file():
        msg = f"File not found: {target}"
        logger.warning(msg)
        return CommandResult(success=False, message=msg, command_type="logs.show")

    try:
        with target.open("r", encoding="utf-8", errors="replace") as fh:
            tail = deque(fh, maxlen=lines)
        result_lines = [line.rstrip("\n") for line in tail]
        logger.info("Read last %d lines from %s", lines, target)
        return CommandResult(
            success=True,
            message="\n".join(result_lines),
            data={"lines": result_lines, "path": str(target)},
            command_type="logs.show",
        )
    except OSError as exc:
        logger.error("Error reading %s: %s", target, exc)
        return CommandResult(
            success=False,
            message=f"Error reading file: {exc}",
            command_type="logs.show",
        )
