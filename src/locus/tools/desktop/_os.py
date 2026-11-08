"""Running OS commands for the desktop tools.

Values from the model never go into a script's text: PowerShell scripts read
them from ``LOCUS_ARG_*`` environment variables, and other commands get them
as separate arguments, so a window title or file name can't inject a command.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from typing import Dict, List, Optional

from locus.core.types import ToolResult

DEFAULT_TIMEOUT = 20.0


def system() -> str:
    """``"windows"``, ``"macos"`` or ``"linux"`` (anything else as reported)."""
    name = platform.system().lower()
    return {"darwin": "macos"}.get(name, name)


@dataclass
class Completed:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def error(self) -> str:
        return (self.stderr or self.stdout).strip() or f"exit code {self.returncode}"


def run(
    args: List[str],
    *,
    env: Optional[Dict[str, str]] = None,
    input: Optional[str] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Completed:
    """Run *args* without a shell and return its output."""
    full_env = {**os.environ, **(env or {})}
    try:
        proc = subprocess.run(
            args,
            input=input,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=full_env,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except FileNotFoundError:
        return Completed(127, "", f"{args[0]} isn't installed")
    except subprocess.TimeoutExpired:
        return Completed(124, "", f"{args[0]} took longer than {timeout:.0f}s")
    return Completed(proc.returncode, proc.stdout or "", proc.stderr or "")


def powershell(
    script: str,
    *,
    args: Optional[Dict[str, str]] = None,
    input: Optional[str] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Completed:
    """Run a PowerShell *script*; *args* arrive as ``$env:LOCUS_ARG_<NAME>``."""
    env = {f"LOCUS_ARG_{k.upper()}": str(v) for k, v in (args or {}).items()}
    prelude = "[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
    if input is not None:
        prelude += "[Console]::InputEncoding = [Text.Encoding]::UTF8; "
    return run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            prelude + script,
        ],
        env=env,
        input=input,
        timeout=timeout,
    )


def has_command(name: str) -> bool:
    return shutil.which(name) is not None


def ok(tool: str, content: str, **metadata) -> ToolResult:
    return ToolResult(tool_name=tool, content=content, success=True, metadata=metadata)


def fail(tool: str, content: str) -> ToolResult:
    return ToolResult(tool_name=tool, content=content, success=False)


def unsupported(tool: str, what: str) -> ToolResult:
    return fail(tool, f"{what} isn't supported on {system()} yet.")


def bad_action(tool: str, action: object, actions: tuple) -> ToolResult:
    return fail(tool, f"Unknown action {action!r}. Use one of: {', '.join(actions)}.")
