"""
AURA — LLM Backend Factory

Instantiates the correct :class:`~core.backends.base.LLMBackend`
based on configuration.  Phase 1 always returns the Ollama stub;
Phase 2 will add provider routing.
"""

from __future__ import annotations

from core.backends.base import LLMBackend
from core.config_loader import get as get_config


def get_backend(
    *,
    mode: str | None = None,
    provider: str | None = None,
    api_key: str | None = None,
) -> LLMBackend:
    """Return an LLM backend appropriate for the current config.

    Parameters
    ----------
    mode:
        ``"offline"`` (default) or ``"api"``.  Falls back to
        ``config.aura.mode``.
    provider:
        Explicit provider name.  Currently only ``"ollama"`` is
        supported.
    api_key:
        API key for cloud providers (reserved for Phase 3+).
    """
    if mode is None:
        mode = get_config("aura.mode", "offline")

    if provider is None:
        provider = get_config("llm.provider", "ollama")

    if provider == "ollama":
        from core.backends.ollama_backend import OllamaBackend

        model = get_config("llm.model", "llama3")
        host = get_config("llm.host", "http://localhost:11434")
        return OllamaBackend(model=model, host=host)

    raise ValueError(f"Unknown LLM provider: {provider!r}")
