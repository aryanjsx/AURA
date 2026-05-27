"""
AURA — Phase 2 Pipeline Schemas.

Shared data structures for the voice pipeline:
  - CommandPlan:     output of BrainController.handle_intent()
  - ExecutionResult: output of CommandEngine.execute()
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CommandPlan:
    """Describes what the CommandEngine should execute."""

    executor: str          # "SYSTEM" | "GIT" | "DOCKER" | "NPM" | "SHELL" | "VISION" | "BROWSER" | "LLM_ONLY"
    action: str            # specific action string
    params: dict[str, Any] = field(default_factory=dict)  # validated parameters
    requires_confirm: bool = False
    is_destructive: bool = False
    timeout_seconds: int = 60
    intent_ref: Any = None  # reference back to IntentObject


@dataclass
class ExecutionResult:
    """Result of a CommandEngine.execute() call."""

    success: bool
    output: str            # human-readable result for TTS
    data: Any = None       # structured result
    error: str | None = None
    executor: str = ""
    duration_ms: int = 0
    was_confirmed: bool = False
