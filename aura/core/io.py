"""
AURA — Input / Output abstractions.

These contracts let the CLI loop (Phase 1 — COMPLETED), voice
listener (Phase 2 — IN PROGRESS), and GUI (Phase 4 — planned) be
swapped without touching the router or executors.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class InputSource(ABC):
    @abstractmethod
    def get_command(self) -> str | None:
        """Return the next command string, or ``None`` to signal exit."""


class OutputSink(ABC):
    @abstractmethod
    def send(self, message: str) -> None:
        """Deliver *message* to the user."""


class StdinInput(InputSource):
    def __init__(self, prompt: str = "\n> ") -> None:
        self._prompt = prompt

    def get_command(self) -> str | None:
        try:
            return input(self._prompt).strip()
        except (EOFError, KeyboardInterrupt):
            return None


class StdoutOutput(OutputSink):
    def send(self, message: str) -> None:
        print(message)
