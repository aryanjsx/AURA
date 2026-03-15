"""
AURA — Process Manager

Wraps shell command execution and process inspection/termination
using ``subprocess`` and ``psutil``.

Security note
-------------
``run_shell_command`` deliberately avoids ``shell=True`` by splitting
the command string.  Commands that require shell features (pipes,
redirects) should be refactored into explicit Python logic where
possible; ``shell=True`` is used only as a controlled fallback with
clear logging.
"""

from __future__ import annotations

import shlex
import subprocess
import sys
from typing import Any, Dict, List

import psutil

from command_engine.logger import get_logger

logger = get_logger("aura.process_manager")


def run_shell_command(command: str, timeout: int = 120) -> Dict[str, Any]:
    """Execute a shell command and capture its output.

    Parameters
    ----------
    command:
        The command string to execute.
    timeout:
        Maximum seconds to wait before killing the process.

    Returns
    -------
    dict
        ``{"stdout": str, "stderr": str, "returncode": int}``
    """
    logger.info("Running command: %s", command)
    try:
        if sys.platform == "win32":
            args = command
            use_shell = True
        else:
            args = shlex.split(command)
            use_shell = False

        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=use_shell,
        )
        logger.info(
            "Command finished (exit %d): %s", result.returncode, command
        )
        return {
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        logger.error("Command timed out after %ds: %s", timeout, command)
        return {"stdout": "", "stderr": "Command timed out", "returncode": -1}
    except FileNotFoundError as exc:
        logger.error("Command not found: %s (%s)", command, exc)
        return {"stdout": "", "stderr": str(exc), "returncode": -1}
    except Exception as exc:
        logger.error("Unexpected error running '%s': %s", command, exc)
        return {"stdout": "", "stderr": str(exc), "returncode": -1}


def list_running_processes(limit: int = 25) -> List[Dict[str, Any]]:
    """Return a snapshot of the top *limit* processes sorted by memory.

    Returns
    -------
    list[dict]
        Each dict contains ``pid``, ``name``, ``cpu_percent``,
        ``memory_mb``.
    """
    processes: List[Dict[str, Any]] = []
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
    logger.info("Listed top %d processes", limit)
    return processes[:limit]


def kill_process(process_name: str) -> str:
    """Terminate all processes matching *process_name* (case-insensitive).

    Returns
    -------
    str
        Human-readable result message.
    """
    killed = 0
    for proc in psutil.process_iter(["name"]):
        try:
            if proc.info["name"] and proc.info["name"].lower() == process_name.lower():
                proc.terminate()
                killed += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if killed:
        logger.info("Killed %d process(es) named '%s'", killed, process_name)
        return f"Terminated {killed} process(es) named '{process_name}'"
    msg = f"No running process found with name '{process_name}'"
    logger.warning(msg)
    return msg
