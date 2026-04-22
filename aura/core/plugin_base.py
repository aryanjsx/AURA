"""
AURA — Plugin base contract.

Every plugin module must define a ``Plugin`` class conforming to this
protocol.  The plugin receives the event bus in its constructor and
exposes two public methods that the loader calls once:

- :meth:`register_commands` returns ``{action: handler | entry_dict}``
- :meth:`register_intents` returns a list of text-to-intent parsers

A plugin's executors **must not be imported directly by any other
module**.  The contract is: pass handlers out through
``register_commands`` or nothing.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable

from aura.core.event_bus import EventBus
from aura.core.intent import Intent
from aura.core.result import CommandResult

IntentParser = Callable[[str], Intent | None]


class Plugin(ABC):
    """Abstract base for every AURA plugin."""

    name: str = ""

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    @abstractmethod
    def register_commands(self) -> dict[str, Any]:
        """Return a mapping of action → handler or ``{handler, description, destructive}``.

        Handler values may be either:
        - a bare callable returning :class:`CommandResult`
        - a dict with keys ``handler`` (callable, required),
          ``description`` (str), ``destructive`` (bool).
        """

    @abstractmethod
    def register_intents(self) -> list[IntentParser]:
        """Return a list of callables ``text -> Intent | None``."""


__all__ = ["Plugin", "IntentParser", "CommandResult"]
