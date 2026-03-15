"""
AURA — Command Dispatcher

Receives a raw text command from the user, parses it, and routes it
to the appropriate handler in the command engine or modules layer.

Routing table
-------------
===============================  ============================
Pattern                          Handler
===============================  ============================
``create file <path>``           file_manager.create_file
``delete file <path>``           file_manager.delete_file
``rename file <old> <new>``      file_manager.rename_file
``move file <src> <dst>``        file_manager.move_file
``search files <dir> <pattern>`` file_manager.search_files
``run command <cmd>``            process_manager.run_shell_command
``list processes``               process_manager.list_running_processes
``kill process <name>``          process_manager.kill_process
``check system health``          system_check.check_system_health
``create project <name>``        project_scaffolder.create_project
``show logs <path> [n]``         log_reader.read_last_lines
===============================  ============================
"""

from __future__ import annotations

import json
from typing import Any

from command_engine.file_manager import (
    create_file,
    delete_file,
    move_file,
    rename_file,
    search_files,
)
from command_engine.logger import get_logger
from command_engine.process_manager import (
    kill_process,
    list_running_processes,
    run_shell_command,
)
from command_engine.system_check import check_system_health
from modules.log_reader import read_last_lines
from modules.project_scaffolder import create_project

logger = get_logger("aura.dispatcher")


def dispatch(command: str) -> str:
    """Parse *command* and delegate to the matching handler.

    Parameters
    ----------
    command:
        A natural-language-style command typed by the user.

    Returns
    -------
    str
        A human-readable response string.
    """
    raw = command.strip()
    if not raw:
        return "No command entered."

    parts = raw.split()
    keyword = parts[0].lower()

    try:
        return _route(parts, keyword, raw)
    except Exception as exc:
        logger.error("Dispatch error for '%s': %s", raw, exc)
        return f"Error: {exc}"


def _route(parts: list[str], keyword: str, raw: str) -> str:
    """Internal routing logic — keeps ``dispatch`` concise."""

    # --- file operations ---
    if keyword == "create" and _word(parts, 1) == "file":
        path = _rest(parts, 2)
        if not path:
            return "Usage: create file <path>"
        return create_file(path)

    if keyword == "delete" and _word(parts, 1) == "file":
        path = _rest(parts, 2)
        if not path:
            return "Usage: delete file <path>"
        return delete_file(path)

    if keyword == "rename" and _word(parts, 1) == "file":
        if len(parts) < 4:
            return "Usage: rename file <old_name> <new_name>"
        return rename_file(parts[2], parts[3])

    if keyword == "move" and _word(parts, 1) == "file":
        if len(parts) < 4:
            return "Usage: move file <source> <destination>"
        return move_file(parts[2], parts[3])

    if keyword == "search" and _word(parts, 1) == "files":
        if len(parts) < 4:
            return "Usage: search files <directory> <pattern>"
        matches = search_files(parts[2], parts[3])
        if not matches:
            return "No files matched."
        return "\n".join(matches)

    # --- process operations ---
    if keyword == "run" and _word(parts, 1) == "command":
        cmd = _rest(parts, 2)
        if not cmd:
            return "Usage: run command <shell_command>"
        result = run_shell_command(cmd)
        return _format_shell_result(result)

    if keyword == "list" and _word(parts, 1) == "processes":
        procs = list_running_processes()
        lines = [
            f"  {p['pid']:>7}  {p['name']:<25} "
            f"CPU {p['cpu_percent']:>5}%  MEM {p['memory_mb']:>8} MB"
            for p in procs
        ]
        return "Top processes:\n" + "\n".join(lines)

    if keyword == "kill" and _word(parts, 1) == "process":
        name = _rest(parts, 2)
        if not name:
            return "Usage: kill process <name>"
        return kill_process(name)

    # --- system health ---
    if raw.lower().startswith("check system health"):
        report = check_system_health()
        return _format_health(report)

    # --- project scaffolding ---
    if keyword == "create" and _word(parts, 1) == "project":
        name = _rest(parts, 2)
        if not name:
            return "Usage: create project <name>"
        return create_project(name)

    # --- log reading ---
    if keyword == "show" and _word(parts, 1) == "logs":
        if len(parts) < 3:
            return "Usage: show logs <file_path> [lines]"
        file_path = parts[2]
        n = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 20
        lines = read_last_lines(file_path, n)
        return "\n".join(lines)

    # --- fallback ---
    logger.warning("Unrecognised command: %s", raw)
    return (
        f"Unknown command: '{raw}'\n"
        "Type 'help' for a list of available commands."
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


def _format_shell_result(result: dict[str, Any]) -> str:
    out = result.get("stdout", "")
    err = result.get("stderr", "")
    code = result.get("returncode", -1)
    sections = []
    if out:
        sections.append(out)
    if err:
        sections.append(f"[stderr] {err}")
    sections.append(f"(exit code {code})")
    return "\n".join(sections)


def _format_health(report: dict[str, str]) -> str:
    lines = []
    for tool, version in report.items():
        if version == "not installed":
            lines.append(f"  {tool:<10} : NOT INSTALLED")
        else:
            lines.append(f"  {tool:<10} : {version}")
    return "System Health:\n" + "\n".join(lines)
