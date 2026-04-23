"""
AURA — Structured Intent.

Produced by the router's text parser (Phase 1 — COMPLETED) or by the
LLM adapter (Phase 2 — IN PROGRESS).  Consumed only through the
command registry — no module should call a handler directly with an
Intent.

Trust model (LOCKDOWN)
----------------------
An :class:`Intent` carries NO ``source`` field.  The caller (Router,
LLM adapter, API handler) must pass ``source=`` explicitly to the
execution entry point and the registry uses that value, not anything
coming from the intent itself.  This prevents a compromised parser or
untrusted input from forging its own source ("cli" / "auto" privilege
escalation) by stuffing a ``source`` attribute into the dataclass.

Constructing an :class:`Intent` with a ``source`` keyword raises a
clear ``TypeError`` — there is no supported way to set it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Intent:
    """Parsed user intention.  ``source`` is intentionally absent."""

    action: str
    args: dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""
    confidence: float = 1.0
    requires_confirm: bool = False
