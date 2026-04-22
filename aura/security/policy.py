"""
AURA — Strict Shell & Process Policy.

Changes vs previous revision
----------------------------
- ``python``, ``node``, ``pip`` are **REMOVED** from the allowlist.  Those
  interpreters accept arbitrary code via ``-c`` / ``-e`` / ``install`` and
  constitute a full RCE vector.
- Argument-level validation is added for commands that *are* allowed but
  still expose code-execution flags (kept defensive in case someone
  re-adds an interpreter).
- Shell metacharacters are rejected inside argv even though
  ``shell=False`` is used — defence in depth.
- Denylist of destructive phrases preserved.
"""

from __future__ import annotations

import shlex
import sys
from pathlib import Path

from aura.core.config_loader import get as get_config
from aura.core.errors import PolicyError

_BLOCKED_EXACT: frozenset[str] = frozenset({
    "rm -rf /",
    "rm -rf /*",
    "rm -rf ~",
    "rm -rf ~/*",
    "halt",
    "poweroff",
    "init 0",
    "init 6",
    "shutdown now",
    "shutdown -h now",
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

# If any of these ever leaks back into the allowlist, these arg-level rules
# deny the arbitrary-code-execution flags those tools provide.
_BLOCKED_ARGS_BY_COMMAND: dict[str, frozenset[str]] = {
    "python": frozenset({"-c", "-m", "--command"}),
    "python3": frozenset({"-c", "-m", "--command"}),
    "py": frozenset({"-c", "-m"}),
    "node": frozenset({"-e", "--eval", "-p", "--print", "--print-and-exit"}),
    "pip": frozenset({"install", "download", "wheel"}),
    "pip3": frozenset({"install", "download", "wheel"}),
    "sh": frozenset({"-c"}),
    "bash": frozenset({"-c"}),
    "zsh": frozenset({"-c"}),
    "powershell": frozenset({"-command", "-c", "-encodedcommand", "-e"}),
    "pwsh": frozenset({"-command", "-c", "-encodedcommand", "-e"}),
    "cmd": frozenset({"/c", "/k"}),
}

# Order matters: multi-character operators MUST appear before the
# single-character ones that are their prefixes, so that a debug scanner
# (or human) reading this list does not mistake ">" alone for ">>" or
# "<" alone for "<<".  The substring check `meta in token` is
# order-independent, but the readability matters.
_SHELL_METACHARACTERS: tuple[str, ...] = (
    ";", "&&", "||", "|", "`", "$(", ">(", "<(",
    ">>", "<<",   # here-docs and append-redirects
    ">", "<",     # file-redirect operators
)

_PROTECTED_PROCESS_NAMES: frozenset[str] = frozenset({
    "system", "system idle process",
    "svchost.exe", "svchost",
    "csrss.exe", "csrss",
    "wininit.exe", "wininit",
    "services.exe", "services",
    "lsass.exe", "lsass",
    "smss.exe", "smss",
    "explorer.exe", "explorer",
    "init", "systemd", "launchd", "kernel_task", "loginwindow",
})


def split_command_string(command: str) -> list[str]:
    """Split a command string into argv tokens without invoking a shell."""
    stripped = (command or "").strip()
    if not stripped:
        return []
    if sys.platform == "win32":
        return shlex.split(stripped, posix=False)
    return shlex.split(stripped)


def _root_executable_name(argv0: str) -> str:
    name = Path(argv0).name.lower()
    if name.endswith(".exe"):
        name = name[:-4]
    if name.endswith(".cmd") or name.endswith(".bat"):
        name = name[:-4]
    return name


class CommandPolicy:
    """Centralised policy for shell execution and process termination."""

    def allowed_commands(self) -> frozenset[str]:
        configured = get_config("shell.allowed_commands") or []
        return frozenset(str(c).strip().lower() for c in configured if c)

    def check_shell_command(self, command: str) -> None:
        """Raise :class:`PolicyError` if *command* is not safe to run."""
        if not command or not command.strip():
            raise PolicyError("Empty command")

        lower = command.lower().strip()
        if lower in _BLOCKED_EXACT:
            raise PolicyError(
                f"Blocked: '{command}' is a destructive command."
            )
        for pattern in _BLOCKED_SUBSTRINGS:
            if pattern in lower:
                raise PolicyError(
                    f"Blocked: command contains dangerous pattern ({pattern!r})."
                )

        argv = split_command_string(command)
        self.check_shell_argv(argv, command)

    def check_shell_argv(self, argv: list[str], original_command: str) -> None:
        """Validate a pre-split argv list."""
        if not argv:
            raise PolicyError("Empty command")

        for token in argv:
            for meta in _SHELL_METACHARACTERS:
                if meta in token:
                    raise PolicyError(
                        f"Blocked: shell metacharacter {meta!r} in argument {token!r}"
                    )

        root = _root_executable_name(argv[0])

        # Arg-level blocks apply whether or not the command is on the
        # allowlist — they prevent accidental interpreter escapes.
        blocked_args = _BLOCKED_ARGS_BY_COMMAND.get(root)
        if blocked_args:
            for arg in argv[1:]:
                if arg.lower() in blocked_args:
                    raise PolicyError(
                        f"Blocked: '{root} {arg}' enables arbitrary code execution."
                    )

        allowed = self.allowed_commands()
        if root not in allowed:
            raise PolicyError(
                f"Blocked: '{root}' is not in shell.allowed_commands. "
                f"Allowed: {sorted(allowed)}"
            )

    def check_kill_target(self, process_name: str) -> None:
        """Raise :class:`PolicyError` if *process_name* is a protected OS process."""
        if not process_name or not process_name.strip():
            raise PolicyError("Process name is required")
        if process_name.lower().strip() in _PROTECTED_PROCESS_NAMES:
            raise PolicyError(
                f"Blocked: '{process_name}' is a protected system process."
            )


_singleton: CommandPolicy | None = None


def get_policy() -> CommandPolicy:
    """Return the shared :class:`CommandPolicy` singleton."""
    global _singleton
    if _singleton is None:
        _singleton = CommandPolicy()
    return _singleton
