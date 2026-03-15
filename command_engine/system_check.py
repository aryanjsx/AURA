"""
AURA — System Health Checker

Probes the local environment for commonly required developer tools
and returns a structured report of their availability and versions.
"""

from __future__ import annotations

import subprocess
import sys
from typing import Dict

from command_engine.logger import get_logger

logger = get_logger("aura.system_check")

_TOOL_COMMANDS: Dict[str, str] = {
    "python": f"{sys.executable} --version",
    "git": "git --version",
    "node": "node --version",
    "docker": "docker --version",
}


def _probe_tool(command: str) -> str:
    """Run *command* and return its trimmed stdout, or ``"not installed"``."""
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=10,
            shell=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        return "not installed"
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return "not installed"


def check_system_health() -> Dict[str, str]:
    """Check availability of developer tools.

    Returns
    -------
    dict[str, str]
        Tool name -> version string or ``"not installed"``.
    """
    report: Dict[str, str] = {}
    for tool, command in _TOOL_COMMANDS.items():
        version_output = _probe_tool(command)
        report[tool] = version_output
        status = "OK" if version_output != "not installed" else "missing"
        logger.info("System check — %s: %s", tool, status)
    return report
