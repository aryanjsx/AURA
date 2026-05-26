"""
AURA — Intelligence Router (Phase 2).

Every voice command passes through this router. It classifies intent,
selects the right model, and decides whether RAG memory retrieval is needed.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from aura.core.ollama_client import OllamaClient, OllamaUnavailableError
from aura.utils.event_bus import EventType, bus

logger = logging.getLogger("aura.router")


class IntentType(str, Enum):
    """All recognized user intent categories."""

    GENERAL_KNOWLEDGE = "GENERAL_KNOWLEDGE"
    CODE_GENERATION = "CODE_GENERATION"
    SYSTEM_COMMAND = "SYSTEM_COMMAND"
    DEV_TASK = "DEV_TASK"
    PROJECT_CONTEXT = "PROJECT_CONTEXT"
    VISION_TASK = "VISION_TASK"
    REALTIME_QUERY = "REALTIME_QUERY"
    UNKNOWN = "UNKNOWN"


@dataclass
class IntentObject:
    """Structured classification result from the router."""

    intent_type: IntentType
    raw_text: str
    cleaned_text: str
    entities: dict[str, Any]
    model_override: str | None
    requires_rag: bool
    confidence: float
    timestamp: datetime = field(default_factory=datetime.now)


_CLASSIFICATION_SYSTEM_PROMPT = """\
You are AURA's intent classifier. Classify the user's command into exactly one intent type.

Return ONLY valid JSON. No explanation. No markdown fences. No preamble. No trailing text.

Schema:
{
  "intent_type": "<INTENT_TYPE>",
  "confidence": <float between 0.0 and 1.0>,
  "entities": { "<key>": "<value>" },
  "requires_rag": <true or false>
}

Valid intent_type values (choose exactly one):
- GENERAL_KNOWLEDGE  — factual questions, explanations, concepts
- CODE_GENERATION    — write, fix, or review code
- SYSTEM_COMMAND     — open/close apps, take screenshot, system control
- DEV_TASK           — git, docker, npm operations
- PROJECT_CONTEXT    — questions about the user's own project files or code
- VISION_TASK        — describe screen, read text on screen
- REALTIME_QUERY     — current prices, latest versions, live data
- UNKNOWN            — anything you cannot confidently classify

Entity keys to extract when present:
- app_name, window_title, action, branch_name, container_name,
  repo_path, language, function_name, filename, task_type"""

# Model selection map: IntentType -> config key under "models"
_MODEL_MAP: dict[IntentType, str] = {
    IntentType.GENERAL_KNOWLEDGE: "general",
    IntentType.CODE_GENERATION: "code",
    IntentType.SYSTEM_COMMAND: "fast",
    IntentType.DEV_TASK: "fast",
    IntentType.PROJECT_CONTEXT: "general",
    IntentType.VISION_TASK: "vision",
    IntentType.REALTIME_QUERY: "general",
    IntentType.UNKNOWN: "general",
}


class IntentRouter:
    """Classifies user intent via LLM and selects the appropriate model."""

    def __init__(self, config: dict, ollama_client: OllamaClient) -> None:
        self._config = config
        self._ollama = ollama_client
        self._models: dict[str, str] = config.get("models", {})
        routing_cfg = config.get("routing", {})
        self._timeout: int = routing_cfg.get("intent_timeout_seconds", 10)
        self._max_retries: int = routing_cfg.get("intent_max_retries", 3)
        self._fast_model: str = self._models.get("fast", "llama3.2:3b")

    def classify(self, raw_text: str) -> IntentObject:
        """Classify a voice-transcribed command into a structured IntentObject."""
        cleaned = raw_text.lower().strip()

        for attempt in range(self._max_retries):
            try:
                response = self._ollama.chat(
                    model=self._fast_model,
                    prompt=cleaned,
                    system_prompt=_CLASSIFICATION_SYSTEM_PROMPT,
                )
                parsed = self._parse_response(response.text)
                if parsed is not None:
                    intent_type = parsed["intent_type"]
                    model_key = _MODEL_MAP.get(intent_type, "general")
                    model_override = self._models.get(model_key, self._fast_model)

                    result = IntentObject(
                        intent_type=intent_type,
                        raw_text=raw_text,
                        cleaned_text=cleaned,
                        entities=parsed.get("entities", {}),
                        model_override=model_override,
                        requires_rag=parsed.get("requires_rag", False),
                        confidence=parsed.get("confidence", 0.5),
                    )
                    bus.emit(
                        EventType.INTENT_CLASSIFIED,
                        {
                            "intent_type": result.intent_type.value,
                            "confidence": result.confidence,
                            "raw_text": raw_text,
                        },
                    )
                    return result

            except OllamaUnavailableError:
                logger.error("Ollama unavailable during classification")
                break
            except Exception as exc:
                logger.warning(
                    "Classification attempt %d/%d failed: %s",
                    attempt + 1,
                    self._max_retries,
                    exc,
                )

            if attempt < self._max_retries - 1:
                time.sleep(1)

        # All retries exhausted — return UNKNOWN
        model_override = self._models.get("general", self._fast_model)
        fallback = IntentObject(
            intent_type=IntentType.UNKNOWN,
            raw_text=raw_text,
            cleaned_text=cleaned,
            entities={},
            model_override=model_override,
            requires_rag=True,
            confidence=0.0,
        )
        bus.emit(
            EventType.INTENT_CLASSIFIED,
            {
                "intent_type": "UNKNOWN",
                "confidence": 0.0,
                "raw_text": raw_text,
                "fallback": True,
            },
        )
        return fallback

    def _parse_response(self, text: str) -> dict[str, Any] | None:
        """Parse JSON from LLM response, returning None on failure."""
        # Strip markdown fences if the model included them
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines)

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            # Try to find JSON object in the response
            start = cleaned.find("{")
            end = cleaned.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    data = json.loads(cleaned[start:end])
                except json.JSONDecodeError:
                    return None
            else:
                return None

        intent_str = data.get("intent_type", "").upper()
        try:
            intent_type = IntentType(intent_str)
        except ValueError:
            return None

        confidence = data.get("confidence", 0.5)
        if not isinstance(confidence, (int, float)):
            confidence = 0.5
        confidence = max(0.0, min(1.0, float(confidence)))

        return {
            "intent_type": intent_type,
            "confidence": confidence,
            "entities": data.get("entities", {}),
            "requires_rag": bool(data.get("requires_rag", False)),
        }
