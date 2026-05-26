"""
AURA — Ollama HTTP Client (Phase 2).

Thin, reliable wrapper around the Ollama REST API. All LLM calls in AURA
go through this single client — nothing else talks to Ollama directly.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import httpx

from aura.utils.event_bus import EventType, bus

logger = logging.getLogger("aura.ollama_client")


@dataclass
class OllamaResponse:
    """Structured response from an Ollama chat/generate call."""

    text: str
    model: str
    duration_ms: int


class OllamaUnavailableError(Exception):
    """Raised when Ollama cannot be reached after all retries."""


class OllamaClient:
    """HTTP client for the local Ollama REST API with retry logic."""

    def __init__(self, config: dict) -> None:
        ollama_cfg = config.get("ollama", {})
        self._base_url: str = ollama_cfg.get("base_url", "http://localhost:11434")
        self._timeout: int = ollama_cfg.get("timeout", 60)
        self._retries: int = ollama_cfg.get("retries", 3)

    def chat(
        self,
        model: str,
        prompt: str,
        system_prompt: str = "",
    ) -> OllamaResponse:
        """Send a chat completion request to Ollama.

        Retries up to config.ollama.retries times with exponential backoff.
        Emits LLM_REQUEST_SENT before and LLM_RESPONSE_RECEIVED after.
        Raises OllamaUnavailableError if all retries fail.
        """
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        bus.emit(EventType.LLM_REQUEST_SENT, {"model": model, "prompt_len": len(prompt)})

        last_exc: Exception | None = None
        for attempt in range(self._retries):
            try:
                start = time.perf_counter()
                response = httpx.post(
                    f"{self._base_url}/api/chat",
                    json={
                        "model": model,
                        "messages": messages,
                        "stream": False,
                        "options": {
                            "num_predict": 150,
                            "temperature": 0.7,
                        },
                    },
                    timeout=self._timeout,
                )
                response.raise_for_status()
                duration_ms = int((time.perf_counter() - start) * 1000)

                data = response.json()
                text = data.get("message", {}).get("content", "")

                result = OllamaResponse(
                    text=text, model=model, duration_ms=duration_ms
                )
                bus.emit(
                    EventType.LLM_RESPONSE_RECEIVED,
                    {"model": model, "duration_ms": duration_ms, "text_len": len(text)},
                )
                return result

            except Exception as exc:
                last_exc = exc
                if attempt < self._retries - 1:
                    backoff = 2 ** (attempt + 1)
                    logger.warning(
                        "Ollama request failed (attempt %d/%d), retrying in %ds: %s",
                        attempt + 1,
                        self._retries,
                        backoff,
                        exc,
                    )
                    time.sleep(backoff)

        bus.emit(
            EventType.SYSTEM_ERROR,
            {"module": "ollama_client", "error": str(last_exc)},
        )
        raise OllamaUnavailableError(
            f"Ollama unavailable after {self._retries} retries: {last_exc}"
        )

    def health_check(self) -> bool:
        """GET /api/tags — returns True if Ollama is reachable."""
        try:
            r = httpx.get(f"{self._base_url}/api/tags", timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    def list_models(self) -> list[str]:
        """Return names of all locally available models."""
        try:
            r = httpx.get(f"{self._base_url}/api/tags", timeout=5)
            r.raise_for_status()
            data = r.json()
            return [m["name"] for m in data.get("models", [])]
        except Exception as exc:
            logger.error("Failed to list models: %s", exc)
            return []
