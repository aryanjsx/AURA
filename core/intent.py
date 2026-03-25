"""
AURA — Structured Intent

Represents a parsed user intention — the bridge between raw text input
(CLI, voice transcript) and the execution layer.  Phase 1 produces
intents via keyword-matched text parsing; Phase 2 will produce them
via LLM inference.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Intent:
    """A structured representation of what the user wants to do.

    Attributes
    ----------
    action:
        Dot-namespaced action identifier (e.g. ``"file.create"``,
        ``"process.shell"``).
    args:
        Keyword arguments forwarded to the handler via
        ``handler(**intent.args)``.
    raw_text:
        The original input that produced this intent (for logging).
    source:
        Origin channel — ``"cli"``, ``"llm"``, or ``"voice"``.
    confidence:
        How certain the parser/LLM is about this intent (0.0–1.0).
        Deterministic CLI parsing always yields ``1.0``.
    """

    action: str
    args: dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""
    source: str = "cli"
    confidence: float = 1.0
