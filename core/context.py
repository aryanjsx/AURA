"""
AURA — Application Context

Lightweight container for cross-cutting concerns (config, policy,
session state) so that components receive a single object instead of
importing globals.  Phase 2 will add the LLM backend and conversation
history here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.config_loader import load_config
from core.policy import CommandPolicy


@dataclass
class AppContext:
    """Shared runtime state passed to components that need it.

    Attributes
    ----------
    config:
        Merged configuration dictionary.
    policy:
        Command safety policy.
    session:
        Mutable dict for per-session state (working directory,
        conversation history, etc.).
    """

    config: dict[str, Any] = field(default_factory=load_config)
    policy: CommandPolicy = field(default_factory=CommandPolicy)
    session: dict[str, Any] = field(default_factory=dict)
