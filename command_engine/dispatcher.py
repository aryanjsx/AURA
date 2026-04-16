"""
AURA — Command Dispatcher

Receives a raw text command, converts it to a structured
:class:`~core.intent.Intent`, and routes it to the matching handler.

Two entry points are provided:

- :func:`dispatch` — accepts a text string (CLI / voice transcript).
- :func:`execute_intent` — accepts a pre-built Intent (LLM output).

Both return a :class:`~core.result.CommandResult`.

Phase 2 pipeline::

    Voice → STT → LLM → Intent → execute_intent() → CommandResult
"""

from __future__ import annotations

from typing import Any, Callable

from command_engine.file_manager import (
    create_file,
    delete_file,
    move_file,
    rename_file,
    search_files,
)
from command_engine.logger import get_logger
from command_engine.npm_executor import run_npm_install, run_npm_script
from command_engine.path_utils import SMART_LOCATIONS
from command_engine.process_manager import (
    get_cpu_usage,
    get_ram_usage,
    kill_process,
    list_running_processes,
    run_shell_command,
)
from command_engine.system_check import check_system_health
from core.intent import Intent
from core.policy import get_policy
from core.result import CommandResult
from modules.log_reader import read_last_lines
from modules.project_scaffolder import create_project

logger = get_logger("aura.dispatcher")

_policy = get_policy()

_PHASE0_HELP_TEXT = """\
AURA - Phase-0 commands

System Monitoring:
  cpu
  cpu usage
  ram
  memory usage
  processes
  show processes

Node:
  npm install [path]
  npm run <script> [path]

Files:
  create file <path>
  delete file <path>

General:
  help
"""


def show_help() -> CommandResult:
    """Return built-in help for Phase-0 CLI commands."""
    logger.info("show_help invoked")
    return CommandResult(
        success=True,
        message=_PHASE0_HELP_TEXT,
        data={"help": "phase0"},
        command_type="show_help",
    )


# ── Command Registry ────────────────────────────────────────────────

COMMAND_REGISTRY: dict[str, Callable[..., CommandResult]] = {
    "show_help": show_help,
    "file.create": create_file,
    "file.delete": delete_file,
    "file.rename": rename_file,
    "file.move": move_file,
    "file.search": search_files,
    "process.shell": run_shell_command,
    "process.list": list_running_processes,
    "get_cpu_usage": get_cpu_usage,
    "get_ram_usage": get_ram_usage,
    "list_processes": list_running_processes,
    "process.kill": kill_process,
    "npm.install": run_npm_install,
    "npm.run": run_npm_script,
    "system.health": check_system_health,
    "project.create": create_project,
    "logs.show": read_last_lines,
}

_COMMAND_DESCRIPTIONS: dict[str, str] = {
    "file.create": "Create an empty file (and parent dirs)",
    "file.delete": "Delete a file",
    "file.rename": "Rename a file",
    "file.move": "Move a file to a new location",
    "file.search": "Search for files by glob pattern",
    "process.shell": "Execute a shell command",
    "process.list": "List top running processes by memory",
    "get_cpu_usage": "Show current CPU utilisation",
    "get_ram_usage": "Show current memory (RAM) utilisation",
    "list_processes": "List top running processes by memory",
    "process.kill": "Terminate processes by name",
    "npm.install": "Run npm install in a project directory",
    "npm.run": "Run an npm script from package.json",
    "system.health": "Check installed developer tools",
    "project.create": "Scaffold a new project directory",
    "logs.show": "Show last N lines of a log file",
    "show_help": "Show Phase-0 command help",
}


def get_available_commands() -> list[dict[str, str]]:
    """Return metadata for every registered command.

    Useful for building LLM system prompts or dynamic help text.
    """
    return [
        {"action": action, "description": _COMMAND_DESCRIPTIONS.get(action, "")}
        for action in COMMAND_REGISTRY
    ]


# ── Public API ──────────────────────────────────────────────────────

def dispatch(command: str) -> CommandResult:
    """Parse *command* text and execute the matching handler.

    This is the backward-compatible entry point used by the CLI loop.

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

    try:
        result = parse_intent(raw)
        if isinstance(result, CommandResult):
            return result
        return execute_intent(result)
    except Exception as exc:
        logger.error("Dispatch error for '%s': %s", raw, exc)
        return CommandResult(success=False, message=f"Error: {exc}")


_LLM_CONFIDENCE_THRESHOLD = 0.6


def execute_intent(intent: Intent) -> CommandResult:
    """Execute a pre-built intent.

    Called by :func:`dispatch` for CLI input and directly by the
    LLM pipeline in Phase 2.

    Pipeline: confidence gate → policy check → registry lookup → handler.
    """
    if intent.source == "llm" and intent.confidence < _LLM_CONFIDENCE_THRESHOLD:
        logger.warning(
            "Low-confidence LLM intent (%.2f): %s",
            intent.confidence,
            intent.action,
        )
        return CommandResult(
            success=False,
            message=(
                f"Low confidence intent ({intent.confidence:.0%}) — "
                f"confirmation required before executing '{intent.action}'."
            ),
            command_type="system.warning",
        )

    violation = _policy.validate_intent(intent)
    if violation:
        logger.warning(
            "Policy blocked intent %s: %s", intent.action, violation,
        )
        return CommandResult(
            success=False, message=violation, command_type=intent.action,
        )

    handler = COMMAND_REGISTRY.get(intent.action)
    if handler is None:
        msg = (
            f"Unknown command: '{intent.raw_text}'\n"
            "Type 'help' for a list of available commands."
            if intent.raw_text
            else f"Unknown action: '{intent.action}'"
        )
        logger.warning("No handler for action: %s", intent.action)
        return CommandResult(success=False, message=msg)

    try:
        return handler(**intent.args)
    except TypeError as exc:
        logger.error("Argument error for %s: %s", intent.action, exc)
        return CommandResult(
            success=False,
            message=f"Invalid arguments for '{intent.action}': {exc}",
            command_type=intent.action,
        )
    except Exception as exc:
        logger.error("Handler error for %s: %s", intent.action, exc)
        return CommandResult(
            success=False,
            message=f"Error: {exc}",
            command_type=intent.action,
        )


# ── Text → Intent Parsing ──────────────────────────────────────────

def parse_intent(command: str) -> Intent | CommandResult:
    """Convert raw CLI text into a structured Intent.

    Recognises file/process/npm/system commands as before, plus common
    phrases for CPU usage, RAM usage, and process listing (e.g. ``cpu``,
    ``get cpu usage``, ``memory usage``, ``show processes``).

    Returns an :class:`Intent` on success, or a :class:`CommandResult`
    with a usage hint when required arguments are missing.
    """
    norm = command.strip().lower()
    if norm == "help" or norm == "--help":
        return Intent(action="show_help", args={}, raw_text=command)

    parts = command.split()
    keyword = parts[0].lower()

    # ── npm (dedicated argv executor) ────────────────────────────

    if keyword == "npm":
        if len(parts) < 2:
            return CommandResult(
                success=False,
                message="Usage: npm install [path] | npm run <script> [path]",
            )
        sub = parts[1].lower()
        if sub == "install":
            cwd = _rest(parts, 2) or "."
            return Intent(
                action="npm.install",
                args={"cwd": cwd},
                raw_text=command,
            )
        if sub == "run":
            if len(parts) < 3:
                return CommandResult(
                    success=False,
                    message="Usage: npm run <script> [project_path]",
                )
            script = parts[2]
            cwd = _rest(parts, 3) or "."
            return Intent(
                action="npm.run",
                args={"script": script, "cwd": cwd},
                raw_text=command,
            )
        return CommandResult(
            success=False,
            message="Usage: npm install [path] | npm run <script> [path]",
        )

    # ── file operations ──────────────────────────────────────────

    if keyword == "create" and _word(parts, 1) == "file":
        path = _rest(parts, 2)
        if not path:
            return CommandResult(success=False, message="Usage: create file <path>")
        return Intent(action="file.create", args={"path": path}, raw_text=command)

    if keyword == "delete" and _word(parts, 1) == "file":
        path = _rest(parts, 2)
        if not path:
            return CommandResult(success=False, message="Usage: delete file <path>")
        return Intent(action="file.delete", args={"path": path}, raw_text=command)

    if keyword == "rename" and _word(parts, 1) == "file":
        if len(parts) < 4:
            return CommandResult(
                success=False, message="Usage: rename file <old_path> <new_name>",
            )
        new_name = parts[-1]
        old_path = " ".join(parts[2:-1])
        return Intent(
            action="file.rename",
            args={"old_name": old_path, "new_name": new_name},
            raw_text=command,
        )

    if keyword == "move" and _word(parts, 1) == "file":
        if len(parts) < 4:
            return CommandResult(
                success=False, message="Usage: move file <source> <destination>",
            )
        src, dst = _split_two_paths(parts[2:])
        return Intent(
            action="file.move",
            args={"source": src, "destination": dst},
            raw_text=command,
        )

    if keyword == "search" and _word(parts, 1) == "files":
        if len(parts) < 4:
            return CommandResult(
                success=False, message="Usage: search files <directory> <pattern>",
            )
        pattern = parts[-1]
        directory = " ".join(parts[2:-1])
        return Intent(
            action="file.search",
            args={"directory": directory, "pattern": pattern},
            raw_text=command,
        )

    # ── process operations ───────────────────────────────────────

    if keyword == "run" and _word(parts, 1) == "command":
        cmd = _rest(parts, 2)
        if not cmd:
            return CommandResult(
                success=False, message="Usage: run command <shell_command>",
            )
        return Intent(
            action="process.shell", args={"command": cmd}, raw_text=command,
        )

    if keyword == "list" and _word(parts, 1) == "processes":
        return Intent(action="process.list", args={}, raw_text=command)

    if keyword == "kill" and _word(parts, 1) == "process":
        name = _rest(parts, 2)
        if not name:
            return CommandResult(
                success=False, message="Usage: kill process <name>",
            )
        return Intent(
            action="process.kill",
            args={"process_name": name},
            raw_text=command,
        )

    # ── system health ────────────────────────────────────────────

    if command.lower().startswith("check system health"):
        return Intent(action="system.health", args={}, raw_text=command)

    # ── project scaffolding ──────────────────────────────────────

    if keyword == "create" and _word(parts, 1) == "project":
        name = _rest(parts, 2)
        if not name:
            return CommandResult(
                success=False, message="Usage: create project <name|path>",
            )
        return Intent(
            action="project.create",
            args={"project_name": name},
            raw_text=command,
        )

    # ── log reading ──────────────────────────────────────────────

    if keyword == "show" and _word(parts, 1) == "logs":
        if len(parts) < 3:
            return CommandResult(
                success=False, message="Usage: show logs <file_path> [lines]",
            )
        if len(parts) > 3 and parts[-1].isdigit():
            n = int(parts[-1])
            file_path = " ".join(parts[2:-1])
        else:
            n = 20
            file_path = _rest(parts, 2)
        return Intent(
            action="logs.show",
            args={"file_path": file_path, "lines": n},
            raw_text=command,
        )

    # ── system monitor (keyword / natural phrases) ─────────────────

    monitor_intent = _parse_system_monitor_phrase(command)
    if monitor_intent is not None:
        return monitor_intent

    # ── fallback ─────────────────────────────────────────────────

    logger.warning("Unrecognised command: %s", command)
    return Intent(action="unknown", args={}, raw_text=command)


# ── System monitor phrase sets (normalised whitespace, lower case) ───────

_CPU_USAGE_PHRASES: frozenset[str] = frozenset({
    "cpu",
    "cpu usage",
    "get cpu",
    "get cpu usage",
    "what is cpu usage",
})

_RAM_USAGE_PHRASES: frozenset[str] = frozenset({
    "ram",
    "memory",
    "ram usage",
    "memory usage",
    "get ram",
    "get memory",
})

_LIST_PROCESSES_PHRASES: frozenset[str] = frozenset({
    "processes",
    "show processes",
    "running processes",
})


def _normalise_monitor_phrase(text: str) -> str:
    """Collapse whitespace and lower-case for phrase matching."""
    return " ".join(text.strip().lower().split())


def _parse_system_monitor_phrase(command: str) -> Intent | None:
    """Map common CPU / RAM / process phrases to monitor intents."""
    norm = _normalise_monitor_phrase(command)
    if norm in _CPU_USAGE_PHRASES:
        return Intent(action="get_cpu_usage", args={}, raw_text=command)
    if norm in _RAM_USAGE_PHRASES:
        return Intent(action="get_ram_usage", args={}, raw_text=command)
    if norm in _LIST_PROCESSES_PHRASES:
        return Intent(action="list_processes", args={}, raw_text=command)
    return None


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

    Falls back to treating the first token as source and the rest as
    destination if no boundary is detected.
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
