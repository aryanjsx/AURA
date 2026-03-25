"""
AURA — LLM Backend Base Class

Defines the contract that every LLM backend (Ollama, OpenAI, etc.)
must satisfy.  Phase 2 will provide concrete implementations; this
module establishes the interface so that consumer code can be written
and tested against the abstraction today.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LLMBackend(ABC):
    """Abstract interface for language-model inference."""

    @abstractmethod
    def complete(
        self,
        prompt: str,
        *,
        system: str = "",
        temperature: float = 0.3,
        max_tokens: int = 512,
    ) -> dict[str, Any]:
        """Send a prompt to the model and return the structured response.

        Returns
        -------
        dict
            Must contain at least ``{"text": "<model output>"}``.
            Implementations may add provider-specific metadata.
        """

    @abstractmethod
    def is_available(self) -> bool:
        """Return ``True`` if the backend is reachable and ready."""
