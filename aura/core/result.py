"""
AURA — Uniform command result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CommandResult:
    """Uniform return type for every registered handler."""

    success: bool
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    command_type: str = ""
    error_code: str | None = None

    def __str__(self) -> str:
        return self.message
