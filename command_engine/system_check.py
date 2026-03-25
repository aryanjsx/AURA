"""
AURA — System Health Checker

Probes the local environment for commonly required developer tools
and returns a structured report of their availability and versions.
The list of tools to check is loaded from config.
"""

from __future__ import annotations

import shlex
import subprocess
import sys

from command_engine.logger import get_logger
from core.config_loader import get as get_config
from core.result import CommandResult

logger = get_logger("aura.system_check")


def _build_tool_commands() -> dict[str, str]:
    """Map each configured tool name to its ``--version`` command."""
    tools: list[str] = get_config("system_check.tools", ["python", "git", "node", "docker"])
    commands: dict[str, str] = {}
    for tool in tools:
        if tool == "python":
            commands[tool] = f"{sys.executable} --version"
        else:
            commands[tool] = f"{tool} --version"
    return commands


def _probe_tool(command: str) -> str:
    """Run *command* and return its trimmed stdout, or ``"not installed"``."""
    try:
        if sys.platform == "win32":
            args: str | list[str] = command
            use_shell = True
        else:
            args = shlex.split(command)
            use_shell = False

        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=10,
            shell=use_shell,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        return "not installed"
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return "not installed"


def check_system_health() -> CommandResult:
    """Check availability of developer tools.

    Returns
    -------
    CommandResult
        ``data["tools"]`` maps tool name → version string or
        ``"not installed"``.
    """
    tool_commands = _build_tool_commands()
    report: dict[str, str] = {}

    for tool, command in tool_commands.items():
        try:
            version_output = _probe_tool(command)
        except Exception as exc:
            logger.error("Probe failed for %s: %s", tool, exc)
            version_output = "not installed"

        report[tool] = version_output
        status = "OK" if version_output != "not installed" else "missing"
        logger.info("System check — %s: %s", tool, status)

    lines: list[str] = []
    for tool, version in report.items():
        if version == "not installed":
            lines.append(f"  {tool:<10} : NOT INSTALLED")
        else:
            lines.append(f"  {tool:<10} : {version}")

    return CommandResult(
        success=True,
        message="System Health:\n" + "\n".join(lines),
        data={"tools": report},
        command_type="system.health",
    )
