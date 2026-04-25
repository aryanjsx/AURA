"""Ollama HTTP client for local LLM inference (Phase 2).

Lives in ``aura.core`` so the main process can use it directly
without crossing the worker import boundary (``plugins.*`` is
import-guarded to the worker subprocess).

.. warning::

   This client uses a **blocking** single-call approach.  On CPU-only
   hardware, long prompts will block the calling thread for the full
   generation time.  Streaming support is tracked as a follow-up.
"""

from __future__ import annotations

import httpx


class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434", timeout: int = 60) -> None:
        self.base_url = base_url
        self.timeout = timeout

    def generate(self, model: str, prompt: str) -> str:
        try:
            response = httpx.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json().get("response", "")
        except Exception as exc:
            return f"[Ollama Error] {exc}"
