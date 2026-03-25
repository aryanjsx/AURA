"""
AURA — Structured Command Result

Provides a uniform return type for all command handlers, enabling
programmatic inspection of success/failure and structured data
alongside human-readable messages.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class CommandResult:
    """Uniform return type for every AURA command handler.

    Attributes
    ----------
    success:
        Whether the command completed without error.
    message:
        Human-readable result text (printed to the console).
    data:
        Optional structured payload for programmatic consumers
        (Phase 2 LLM, GUI widgets, etc.).
    command_type:
        Short label identifying the command category.
    """

    success: bool
    message: str
    data: dict[str, Any] | None = None
    command_type: str = ""

    def __str__(self) -> str:
        """Allow ``print(result)`` to display the message directly."""
        return self.message
