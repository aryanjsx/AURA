"""
AURA — LLM Brain

High-level interface that accepts natural-language text and returns
a structured :class:`~core.intent.Intent`.  Phase 1 uses a stub that
returns a mock intent; Phase 2 will delegate to a real LLM backend
for intent classification and argument extraction.
"""

from __future__ import annotations

from command_engine.logger import get_logger
from core.backends.base import LLMBackend
from core.intent import Intent

logger = get_logger("aura.llm_brain")


class LLMBrain:
    """Translates natural language into structured intents.

    Parameters
    ----------
    backend:
        The LLM backend used for inference.
    """

    def __init__(self, backend: LLMBackend) -> None:
        self.backend = backend

    def process(self, text: str) -> Intent:
        """Analyse *text* and return the most likely intent.

        When the backend is unavailable (Phase 1 default) the method
        returns a low-confidence ``"passthrough"`` intent so the caller
        can fall back to text-based dispatch.  Phase 2 will build a
        prompt from the command registry and parse the LLM response
        into a fully structured intent.
        """
        if not self.backend.is_available():
            logger.debug(
                "LLM backend unavailable — returning passthrough intent",
            )
            return Intent(
                action="passthrough",
                args={"raw": text},
                raw_text=text,
                source="llm",
                confidence=0.0,
            )

        logger.info("Processing text via LLM: %s", text[:80])
        response = self.backend.complete(
            prompt=text,
            system=(
                "You are AURA, a developer assistant. "
                "Parse the user's intent into an action and arguments."
            ),
        )

        return Intent(
            action="file.create",
            args={"path": "test.txt"},
            raw_text=text,
            source="llm",
            confidence=0.5,
        )
