# aura/schemas/command.py
# AURA Command Schema — CommandPlan and ExecutionResult.

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from aura.schemas.intent import IntentObject


class ExecutorType(Enum):
    SYSTEM   = auto()   # open/close apps, shutdown, restart, screenshot, volume
    SHELL    = auto()   # allowlisted shell commands
    MONITOR  = auto()   # CPU, RAM, battery, process list
    SESSION  = auto()   # session control (end session via voice command)
    GIT      = auto()   # Phase 3
    DOCKER   = auto()   # Phase 3
    NPM      = auto()   # Phase 3
    BROWSER  = auto()   # Phase 7
    VISION   = auto()   # Phase 4
    LLM_ONLY = auto()   # No executor — response goes straight to TTS


@dataclass
class CommandPlan:
    executor:          ExecutorType
    action:            str
    params:            dict[str, Any]  = field(default_factory=dict)
    requires_confirm:  bool            = False
    is_destructive:    bool            = False
    timeout_seconds:   int             = 30
    intent_ref:        IntentObject | None = None


@dataclass
class ExecutionResult:
    success:       bool
    output:        str              # human-readable — goes to TTS
    data:          Any              = None
    error:         str | None       = None
    executor:      ExecutorType | None = None
    duration_ms:   int              = 0
    was_confirmed: bool             = False
