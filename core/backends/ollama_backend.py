"""
AURA — Ollama LLM Backend (stub)

Placeholder implementation for Phase 2.  Returns canned responses so
that the intent → LLM → execution pipeline can be developed and tested
end-to-end before a real Ollama server is wired up.
"""

from __future__ import annotations

from typing import Any

from command_engine.logger import get_logger
from core.backends.base import LLMBackend

logger = get_logger("aura.backend.ollama")


class OllamaBackend(LLMBackend):
    """Stub Ollama backend — returns mock responses."""

    def __init__(
        self,
        model: str = "llama3",
        host: str = "http://localhost:11434",
    ) -> None:
        self._model = model
        self._host = host

    def complete(
        self,
        prompt: str,
        *,
        system: str = "",
        temperature: float = 0.3,
        max_tokens: int = 512,
    ) -> dict[str, Any]:
        logger.info(
            "OllamaBackend.complete() called (stub) — model=%s", self._model,
        )
        return {
            "text": "",
            "model": self._model,
            "stub": True,
        }

    def is_available(self) -> bool:
        return False
