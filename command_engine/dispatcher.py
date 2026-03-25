"""
AURA — Command Dispatcher

Receives a raw text command from the user, parses it, and routes it
to the appropriate handler in the command engine or modules layer.

All path arguments are forwarded as-is to the handler functions, which
internally call :func:`~command_engine.path_utils.resolve_path` for
safe, absolute resolution (``~``, smart keywords, cross-platform).

Every handler returns a :class:`~core.result.CommandResult`; the
dispatcher passes it through unchanged so that callers (CLI, GUI,
LLM layer) can inspect both the human-readable message and the
structured data.

Routing table
-------------
====================================  ==============================
Pattern                               Handler
====================================  ==============================
``create file <path>``                file_manager.create_file
``delete file <path>``                file_manager.delete_file
``rename file <old> <new>``           file_manager.rename_file
``move file <src> <dst>``             file_manager.move_file
``search files <dir> <pattern>``      file_manager.search_files
``run command <cmd>``                 process_manager.run_shell_command
``list processes``                    process_manager.list_running_processes
``kill process <name>``               process_manager.kill_process
``check system health``               system_check.check_system_health
``create project <name|path>``        project_scaffolder.create_project
``show logs <path> [n]``              log_reader.read_last_lines
====================================  ==============================
"""

from __future__ import annotations

from command_engine.file_manager import (
    create_file,
    delete_file,
    move_file,
    rename_file,
    search_files,
)
from command_engine.logger import get_logger
from command_engine.path_utils import SMART_LOCATIONS
from command_engine.process_manager import (
    kill_process,
    list_running_processes,
    run_shell_command,
)
from command_engine.system_check import check_system_health
from core.result import CommandResult
from modules.log_reader import read_last_lines
from modules.project_scaffolder import create_project

logger = get_logger("aura.dispatcher")


def dispatch(command: str) -> CommandResult:
    """Parse *command* and delegate to the matching handler.

    Parameters
    ----------
    command:
        A natural-language-style command typed by the user.

    Returns
    -------
    CommandResult
        Structured result containing a human-readable message and
        optional data payload.
    """
    raw = command.strip()
    if not raw:
        return CommandResult(success=False, message="No command entered.")

    parts = raw.split()
    keyword = parts[0].lower()

    try:
        return _route(parts, keyword, raw)
    except Exception as exc:
        logger.error("Dispatch error for '%s': %s", raw, exc)
        return CommandResult(success=False, message=f"Error: {exc}")


def _route(parts: list[str], keyword: str, raw: str) -> CommandResult:
    """Internal routing logic — keeps ``dispatch`` concise."""

    # ── file operations ──────────────────────────────────────────────

    if keyword == "create" and _word(parts, 1) == "file":
        path = _rest(parts, 2)
        if not path:
            return CommandResult(success=False, message="Usage: create file <path>")
        return create_file(path)

    if keyword == "delete" and _word(parts, 1) == "file":
        path = _rest(parts, 2)
        if not path:
            return CommandResult(success=False, message="Usage: delete file <path>")
        return delete_file(path)

    if keyword == "rename" and _word(parts, 1) == "file":
        if len(parts) < 4:
            return CommandResult(
                success=False, message="Usage: rename file <old_path> <new_name>"
            )
        new_name = parts[-1]
        old_path = " ".join(parts[2:-1])
        return rename_file(old_path, new_name)

    if keyword == "move" and _word(parts, 1) == "file":
        if len(parts) < 4:
            return CommandResult(
                success=False, message="Usage: move file <source> <destination>"
            )
        src, dst = _split_two_paths(parts[2:])
        return move_file(src, dst)

    if keyword == "search" and _word(parts, 1) == "files":
        if len(parts) < 4:
            return CommandResult(
                success=False, message="Usage: search files <directory> <pattern>"
            )
        pattern = parts[-1]
        directory = " ".join(parts[2:-1])
        return search_files(directory, pattern)

    # ── process operations ───────────────────────────────────────────

    if keyword == "run" and _word(parts, 1) == "command":
        cmd = _rest(parts, 2)
        if not cmd:
            return CommandResult(
                success=False, message="Usage: run command <shell_command>"
            )
        return run_shell_command(cmd)

    if keyword == "list" and _word(parts, 1) == "processes":
        return list_running_processes()

    if keyword == "kill" and _word(parts, 1) == "process":
        name = _rest(parts, 2)
        if not name:
            return CommandResult(
                success=False, message="Usage: kill process <name>"
            )
        return kill_process(name)

    # ── system health ────────────────────────────────────────────────

    if raw.lower().startswith("check system health"):
        return check_system_health()

    # ── project scaffolding ──────────────────────────────────────────

    if keyword == "create" and _word(parts, 1) == "project":
        name = _rest(parts, 2)
        if not name:
            return CommandResult(
                success=False, message="Usage: create project <name|path>"
            )
        return create_project(name)

    # ── log reading ──────────────────────────────────────────────────

    if keyword == "show" and _word(parts, 1) == "logs":
        if len(parts) < 3:
            return CommandResult(
                success=False, message="Usage: show logs <file_path> [lines]"
            )
        if len(parts) > 3 and parts[-1].isdigit():
            n = int(parts[-1])
            file_path = " ".join(parts[2:-1])
        else:
            n = 20
            file_path = _rest(parts, 2)
        return read_last_lines(file_path, n)

    # ── fallback ─────────────────────────────────────────────────────

    logger.warning("Unrecognised command: %s", raw)
    return CommandResult(
        success=False,
        message=(
            f"Unknown command: '{raw}'\n"
            "Type 'help' for a list of available commands."
        ),
    )


# ── Helpers ──────────────────────────────────────────────────────────

def _word(parts: list[str], index: int) -> str:
    """Return lowered word at *index*, or empty string if out of range."""
    if index < len(parts):
        return parts[index].lower()
    return ""


def _rest(parts: list[str], start: int) -> str:
    """Re-join parts from *start* onward."""
    return " ".join(parts[start:])


def _split_two_paths(tokens: list[str]) -> tuple[str, str]:
    """Split a token list into two path strings.

    Heuristic: scan left-to-right for the first token that looks like
    the start of a second path (starts with ``~``, ``/``, a drive
    letter, or a smart-location keyword).  Everything before it is the
    source path; everything from it onward is the destination.

    Falls back to splitting at the midpoint if no boundary is detected.
    """
    for i in range(1, len(tokens)):
        t = tokens[i]
        lower = t.lower().rstrip("/\\")
        if (
            t.startswith("~")
            or t.startswith("/")
            or (len(t) >= 2 and t[1] == ":")
            or lower in SMART_LOCATIONS
        ):
            return " ".join(tokens[:i]), " ".join(tokens[i:])

    return tokens[0], " ".join(tokens[1:])
