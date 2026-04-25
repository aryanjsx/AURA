"""Memory plugin — persistent semantic context via RAG (Phase 6 stub)."""

from __future__ import annotations

from typing import Any

from aura.core.event_bus import EventBus
from aura.core.plugin_base import IntentParser, Plugin as PluginBase


class Plugin(PluginBase):
    name = "memory"

    def __init__(self, bus: EventBus) -> None:
        super().__init__(bus)

    def register_commands(self) -> dict[str, Any]:
        return {}

    def register_intents(self) -> list[IntentParser]:
        return []
