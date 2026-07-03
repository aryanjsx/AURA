# aura/schemas/intent.py
# AURA Intent Schema — do not import from other AURA modules here.

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any


class IntentType(Enum):
    GENERAL_KNOWLEDGE  = auto()
    CODE_GENERATION    = auto()
    SYSTEM_COMMAND     = auto()
    DEV_TASK           = auto()
    PROJECT_CONTEXT    = auto()
    VISION_TASK        = auto()
    REALTIME_QUERY     = auto()
    FILE_OPERATION     = auto()
    DEACTIVATE_SESSION = auto()
    UNKNOWN            = auto()


@dataclass
class IntentObject:
    intent_type:    IntentType
    raw_text:       str
    cleaned_text:   str
    entities:       dict[str, Any]     = field(default_factory=dict)
    model_override: str | None         = None
    requires_rag:   bool               = False
    confidence:     float              = 0.0
    timestamp:      datetime           = field(default_factory=datetime.now)
