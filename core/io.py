"""
AURA — Input / Output Abstraction

Defines the contracts for command input and result output so that
the CLI loop (Phase 1), voice pipeline (Phase 2), and GUI (Phase 4)
can be swapped without touching the dispatcher or executors.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class InputSource(ABC):
    """Contract: something that yields user commands."""

    @abstractmethod
    def get_command(self) -> str | None:
        """Return the next command string, or ``None`` to signal exit."""


class OutputSink(ABC):
    """Contract: something that presents results to the user."""

    @abstractmethod
    def send(self, message: str) -> None:
        """Display or speak *message*."""


class StdinInput(InputSource):
    """Read commands from stdin (interactive terminal)."""

    def __init__(self, prompt: str = "\n> ") -> None:
        self._prompt = prompt

    def get_command(self) -> str | None:
        try:
            return input(self._prompt).strip()
        except (EOFError, KeyboardInterrupt):
            return None


class StdoutOutput(OutputSink):
    """Print results to stdout."""

    def send(self, message: str) -> None:
        print(message)
