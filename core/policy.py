"""
AURA — Command Policy Layer

Centralised safety validation for all command execution.  Every intent
passes through the policy before the handler is invoked — both in the
CLI dispatcher and (in Phase 2) in the LLM execution pipeline.

The blocked-pattern lists are the single source of truth for shell
command safety.  ``process_manager`` and ``dispatcher`` both delegate
to :class:`CommandPolicy` rather than maintaining their own checks.
"""

from __future__ import annotations

from command_engine.logger import get_logger
from core.intent import Intent

logger = get_logger("aura.policy")

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


class CommandPolicy:
    """Gate-keeper that blocks dangerous operations before execution."""

    def validate_intent(self, intent: Intent) -> str | None:
        """Return an error message if *intent* is blocked, ``None`` if safe.

        Currently only shell commands are validated; file-path safety
        is handled separately by ``path_utils.validate_not_protected``.
        """
        if intent.action == "process.shell":
            return self.check_shell_command(intent.args.get("command", ""))
        return None

    def check_shell_command(self, command: str) -> str | None:
        """Return an error message if *command* matches a blocked pattern.

        Returns ``None`` when the command is safe to execute.
        """
        lower = command.lower().strip()

        if lower in _BLOCKED_EXACT:
            return f"Blocked: '{command}' is a destructive command."

        for pattern in _BLOCKED_SUBSTRINGS:
            if pattern in lower:
                return (
                    f"Blocked: command contains dangerous pattern ('{pattern}'). "
                    f"Run it directly in your terminal if this is intentional."
                )

        return None
