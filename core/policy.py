"""
AURA — Command Policy Layer

Centralised safety validation for all command execution.  Every intent
passes through the policy before the handler is invoked — both in the
CLI dispatcher and (in Phase 2) in the LLM execution pipeline.

Shell commands are validated with a **hybrid model**: destructive
patterns are blocked by a denylist, and only executables in the
allowlist may be invoked.  All modules share a single
:class:`CommandPolicy` instance from :func:`get_policy`.
"""

from __future__ import annotations

import shlex
import sys
from pathlib import Path

from core.intent import Intent

# Root executable names (lowercase, no extension) permitted for
# ``run command`` / ``process.shell``.  Includes common interpreters
# and helpers used by tests and local workflows.
ALLOWED_COMMANDS: frozenset[str] = frozenset({
    "git",
    "npm",
    "docker",
    "node",
    "python",
    "pip",
    "pip3",
    "py",
    "python3",
    "echo",
})

_BLOCKED_EXACT: frozenset[str] = frozenset({
    "rm -rf /",
    "rm -rf /*",
    "rm -rf ~",
    "rm -rf ~/*",
    "halt",
    "poweroff",
    "init 0",
    "init 6",
})

_BLOCKED_SUBSTRINGS: tuple[str, ...] = (
    "mkfs.",
    "mkfs ",
    ":(){",
    "dd if=/dev/zero",
    "dd if=/dev/random",
    "dd if=/dev/urandom",
    "> /dev/sd",
    "format c:",
    "format d:",
    "del /s /q c:\\",
    "del /s /q c:/",
    "rd /s /q c:\\",
    "rd /s /q c:/",
)

_PROTECTED_PROCESS_NAMES: frozenset[str] = frozenset({
    "system",
    "system idle process",
    "svchost.exe",
    "svchost",
    "csrss.exe",
    "csrss",
    "wininit.exe",
    "wininit",
    "services.exe",
    "services",
    "lsass.exe",
    "lsass",
    "smss.exe",
    "smss",
    "explorer.exe",
    "explorer",
    "init",
    "systemd",
    "launchd",
    "kernel_task",
    "loginwindow",
})


def split_command_string(command: str) -> list[str]:
    """Split a user command string into argv tokens without invoking a shell.

    Uses POSIX rules on Unix and Windows-friendly rules on Windows so
    quoted segments are preserved.
    """
    stripped = command.strip()
    if not stripped:
        return []
    if sys.platform == "win32":
        return shlex.split(stripped, posix=False)
    return shlex.split(stripped)


def _root_executable_name(argv0: str) -> str:
    """Normalise argv[0] to a bare command name for allowlist checks."""
    name = Path(argv0).name
    lower = name.lower()
    if lower.endswith(".exe"):
        lower = lower[:-4]
    return lower


class CommandPolicy:
    """Gate-keeper that blocks dangerous operations before execution."""

    def validate_intent(self, intent: Intent) -> str | None:
        """Return an error message if *intent* is blocked, ``None`` if safe."""
        if intent.action == "process.shell":
            return self.check_shell_command(intent.args.get("command", ""))
        if intent.action == "process.kill":
            return self.check_kill_target(intent.args.get("process_name", ""))
        if intent.action in ("npm.install", "npm.run"):
            return None
        return None

    def check_shell_argv(self, argv: list[str], original_command: str) -> str | None:
        """Validate a pre-split argv with denylist + allowlist rules.

        Parameters
        ----------
        argv:
            Executable and arguments; must be non-empty.
        original_command:
            Raw user string for denylist matching (preserves spacing).
        """
        lower = original_command.lower().strip()

        if lower in _BLOCKED_EXACT:
            return f"Blocked: '{original_command}' is a destructive command."

        for pattern in _BLOCKED_SUBSTRINGS:
            if pattern in lower:
                return (
                    f"Blocked: command contains dangerous pattern ('{pattern}'). "
                    f"Run it directly in your terminal if this is intentional."
                )

        root = _root_executable_name(argv[0])
        if root not in ALLOWED_COMMANDS:
            return (
                f"Blocked: '{root}' is not an allowed command. "
                f"Allowed tools include: {', '.join(sorted(ALLOWED_COMMANDS))}."
            )

        return None

    def check_shell_command(self, command: str) -> str | None:
        """Return an error message if *command* is blocked, ``None`` if safe."""
        argv = split_command_string(command)
        if not argv:
            return "Blocked: empty command."
        return self.check_shell_argv(argv, command)

    def check_kill_target(self, process_name: str) -> str | None:
        """Return an error message if *process_name* is a protected OS process."""
        if process_name.lower().strip() in _PROTECTED_PROCESS_NAMES:
            return (
                f"Blocked: '{process_name}' is a protected system process. "
                f"Terminating it could destabilise the operating system."
            )
        return None


_singleton: CommandPolicy | None = None


def get_policy() -> CommandPolicy:
    """Return the shared :class:`CommandPolicy` singleton."""
    global _singleton
    if _singleton is None:
        _singleton = CommandPolicy()
    return _singleton
