"""
AURA — Process Manager

Wraps shell command execution and process inspection/termination
using ``subprocess`` and ``psutil``.

Security note
-------------
``run_shell_command`` validates every command against the centralized
:class:`~core.policy.CommandPolicy` before execution.  Commands are
split into argv with :func:`~core.policy.split_command_string` and run
**without** ``shell=True`` to avoid shell injection.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import psutil

from command_engine.logger import get_logger
from core.config_loader import get as get_config
from core.policy import get_policy, split_command_string
from core.result import CommandResult

logger = get_logger("aura.process_manager")

_policy = get_policy()


def safe_run_command(
    cmd: list[str],
    cwd: Path | None = None,
    timeout: int | None = None,
    command_type: str = "process.shell",
) -> CommandResult:
    """Execute *cmd* as argv (no shell) and capture stdout/stderr.

    Parameters
    ----------
    cmd:
        Executable path or name followed by arguments.
    cwd:
        Optional working directory for the child process.
    timeout:
        Seconds before the process is killed; defaults to ``shell.timeout``.
    command_type:
        Label stored on the returned :class:`~core.result.CommandResult`.

    Returns
    -------
    CommandResult
        Contains stdout, stderr, and return code in *data*.
    """
    if not cmd:
        return CommandResult(
            success=False,
            message="Error: empty command list.",
            data={"stdout": "", "stderr": "", "returncode": -1},
            command_type=command_type,
        )

    if timeout is None:
        timeout = int(get_config("shell.timeout", 120))

    display = " ".join(cmd)
    logger.info("Running argv command: %s", display)

    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )

        out = result.stdout.strip()
        err = result.stderr.strip()
        code = result.returncode

        sections: list[str] = []
        if out:
            sections.append(out)
        if err:
            sections.append(f"[stderr] {err}")
        sections.append(f"(exit code {code})")
        message = "\n".join(sections)

        logger.info("Command finished (exit %d): %s", code, display)
        return CommandResult(
            success=code == 0,
            message=message,
            data={"stdout": out, "stderr": err, "returncode": code},
            command_type=command_type,
        )

    except subprocess.TimeoutExpired:
        logger.error("Command timed out after %ds: %s", timeout, display)
        return CommandResult(
            success=False,
            message=f"Command timed out after {timeout}s",
            data={"stdout": "", "stderr": "Command timed out", "returncode": -1},
            command_type=command_type,
        )
    except FileNotFoundError as exc:
        logger.error("Command not found: %s (%s)", display, exc)
        return CommandResult(
            success=False,
            message=f"Command not found: {exc}",
            data={"stdout": "", "stderr": str(exc), "returncode": -1},
            command_type=command_type,
        )
    except Exception as exc:
        logger.error("Unexpected error running '%s': %s", display, exc)
        return CommandResult(
            success=False,
            message=f"Error: {exc}",
            data={"stdout": "", "stderr": str(exc), "returncode": -1},
            command_type=command_type,
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_shell_command(
    command: str,
    timeout: int | None = None,
) -> CommandResult:
    """Execute a shell command and capture its output.

    Parameters
    ----------
    command:
        The command string to execute (parsed into argv; no shell).
    timeout:
        Maximum seconds to wait before killing the process.
        Defaults to the ``shell.timeout`` config value (120 s).

    Returns
    -------
    CommandResult
        Contains stdout, stderr, and return code in *data*.
    """
    argv = split_command_string(command)
    if not argv:
        return CommandResult(
            success=False,
            message="Blocked: empty command.",
            command_type="process.shell",
        )

    blocked = _policy.check_shell_argv(argv, command)
    if blocked:
        logger.warning(blocked)
        return CommandResult(
            success=False, message=blocked, command_type="process.shell",
        )

    if timeout is None:
        timeout = int(get_config("shell.timeout", 120))

    return safe_run_command(argv, cwd=None, timeout=timeout, command_type="process.shell")


def get_cpu_usage() -> CommandResult:
    """Report current aggregate CPU utilisation (percent)."""
    pct = psutil.cpu_percent(interval=0.1)
    message = f"CPU usage: {pct}%"
    logger.info("CPU usage snapshot: %s%%", pct)
    return CommandResult(
        success=True,
        message=message,
        data={"cpu_percent": pct},
        command_type="get_cpu_usage",
    )


def get_ram_usage() -> CommandResult:
    """Report virtual memory (RAM) usage."""
    vm = psutil.virtual_memory()
    used_gb = vm.used / (1024**3)
    total_gb = vm.total / (1024**3)
    message = (
        f"Memory usage: {vm.percent}% "
        f"({used_gb:.2f} GiB used / {total_gb:.2f} GiB total)"
    )
    logger.info("RAM usage snapshot: %s%%", vm.percent)
    return CommandResult(
        success=True,
        message=message,
        data={
            "percent": vm.percent,
            "used_bytes": vm.used,
            "total_bytes": vm.total,
        },
        command_type="get_ram_usage",
    )


def list_running_processes(limit: int = 25) -> CommandResult:
    """Return a snapshot of the top *limit* processes sorted by memory.

    Returns
    -------
    CommandResult
        ``data["processes"]`` contains the list of process dicts.
    """
    processes: list[dict[str, Any]] = []
    for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info"]):
        try:
            info = proc.info
            processes.append({
                "pid": info["pid"],
                "name": info["name"],
                "cpu_percent": info["cpu_percent"],
                "memory_mb": round(
                    (info["memory_info"].rss if info["memory_info"] else 0)
                    / (1024 * 1024),
                    1,
                ),
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    processes.sort(key=lambda p: p["memory_mb"], reverse=True)
    top = processes[:limit]

    lines = [
        f"  {p['pid']:>7}  {p['name']:<25} "
        f"CPU {p['cpu_percent']:>5}%  MEM {p['memory_mb']:>8} MB"
        for p in top
    ]
    message = "Top processes:\n" + "\n".join(lines)

    logger.info("Listed top %d processes", limit)
    return CommandResult(
        success=True,
        message=message,
        data={"processes": top},
        command_type="process.list",
    )


def kill_process(process_name: str) -> CommandResult:
    """Terminate all processes matching *process_name* (case-insensitive).

    Protected system processes are blocked by :class:`CommandPolicy`.

    Returns
    -------
    CommandResult
    """
    blocked = _policy.check_kill_target(process_name)
    if blocked:
        logger.warning(blocked)
        return CommandResult(
            success=False, message=blocked, command_type="process.kill",
        )

    killed = 0
    for proc in psutil.process_iter(["name"]):
        try:
            if (
                proc.info["name"]
                and proc.info["name"].lower() == process_name.lower()
            ):
                proc.terminate()
                killed += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if killed:
        logger.info("Killed %d process(es) named '%s'", killed, process_name)
        return CommandResult(
            success=True,
            message=f"Terminated {killed} process(es) named '{process_name}'",
            data={"killed": killed, "name": process_name},
            command_type="process.kill",
        )

    msg = f"No running process found with name '{process_name}'"
    logger.warning(msg)
    return CommandResult(
        success=False,
        message=msg,
        data={"killed": 0, "name": process_name},
        command_type="process.kill",
    )
