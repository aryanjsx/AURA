"""
AURA — Brain Controller (Phase 2).

Receives a classified IntentObject from the IntentRouter, selects the
appropriate LLM model from config, builds a CommandPlan, and emits
COMMAND_PLAN_READY on the EventBus.

Model selection rules:
  SYSTEM_COMMAND / DEV_TASK  → config.models.fast
  CODE_GENERATION            → config.models.code
  PROJECT_CONTEXT / UNKNOWN  → config.models.general (+ requires_rag=True)
  GENERAL_KNOWLEDGE          → config.models.general
  VISION_TASK                → config.models.vision
  REALTIME_QUERY             → config.models.general
"""

from __future__ import annotations

import logging
from typing import Any

from aura.core.schemas import CommandPlan

logger = logging.getLogger("aura.brain")

# IntentType string → (config models key, executor, requires_rag)
_INTENT_DISPATCH: dict[str, tuple[str, str, bool]] = {
    "SYSTEM_COMMAND":     ("fast",    "SYSTEM",   False),
    "DEV_TASK":           ("fast",    "SHELL",    False),
    "CODE_GENERATION":    ("code",    "LLM_ONLY", False),
    "PROJECT_CONTEXT":    ("general", "LLM_ONLY", True),
    "UNKNOWN":            ("general", "LLM_ONLY", True),
    "GENERAL_KNOWLEDGE":  ("general", "LLM_ONLY", False),
    "VISION_TASK":        ("vision",  "VISION",   False),
    "REALTIME_QUERY":     ("general", "LLM_ONLY", False),
}

# Actions that are considered destructive and require safety gate
_DESTRUCTIVE_ACTIONS: frozenset[str] = frozenset({
    "delete_file", "delete_folder", "rmdir",
    "git_push", "git_reset_hard", "git_branch_delete", "git_force_push",
    "docker_remove", "docker_prune",
    "kill_process",
})


class BrainController:
    """Translates classified intents into executable CommandPlans."""

    def __init__(self, config: dict[str, Any], event_bus: Any, ollama_client: Any) -> None:
        self._config = config
        self._event_bus = event_bus
        self._ollama = ollama_client
        self._models: dict[str, str] = config.get("models", {})

    def handle_intent(self, intent_object: Any) -> CommandPlan:
        """Build a CommandPlan from the classified intent and emit COMMAND_PLAN_READY.

        Parameters
        ----------
        intent_object : IntentObject
            The classified intent from IntentRouter.

        Returns
        -------
        CommandPlan
            The plan ready for CommandEngine.execute().
        """
        intent_type = intent_object.intent_type
        intent_type_str = intent_type.value if hasattr(intent_type, "value") else str(intent_type)

        model_key, executor, requires_rag = _INTENT_DISPATCH.get(
            intent_type_str, ("general", "LLM_ONLY", True)
        )

        model = self._models.get(model_key, self._models.get("general", ""))
        if intent_object.model_override:
            model = intent_object.model_override

        # Determine action from entities or intent type
        action = self._resolve_action(intent_type_str, intent_object.entities, intent_object.cleaned_text)
        is_destructive = action in _DESTRUCTIVE_ACTIONS

        # Build params
        params: dict[str, Any] = {
            "model": model,
            "prompt": intent_object.cleaned_text,
            "raw_text": intent_object.raw_text,
            "requires_rag": requires_rag or intent_object.requires_rag,
        }
        params.update(intent_object.entities)

        plan = CommandPlan(
            executor=executor,
            action=action,
            params=params,
            requires_confirm=is_destructive,
            is_destructive=is_destructive,
            timeout_seconds=self._config.get("ollama", {}).get("timeout", 60),
            intent_ref=intent_object,
        )

        logger.info(
            "CommandPlan: executor=%s action=%s model=%s destructive=%s",
            plan.executor, plan.action, model, plan.is_destructive,
        )

        from aura.core.event_bus import EventType
        self._event_bus.emit(EventType.COMMAND_PLAN_READY, {"command_plan": plan})
        return plan

    @staticmethod
    def _resolve_action(intent_type_str: str, entities: dict[str, Any], text: str) -> str:
        """Derive a concrete action string from intent + entities."""
        if entities.get("action"):
            return str(entities["action"])

        # Fallback heuristics based on intent type
        if intent_type_str == "SYSTEM_COMMAND":
            lower = text.lower()
            if any(kw in lower for kw in ("open", "launch", "start")):
                return "open_app"
            if any(kw in lower for kw in ("kill", "stop", "close", "end")):
                return "kill_process"
            if any(kw in lower for kw in ("cpu", "ram", "memory", "battery", "disk")):
                return "get_stats"
            if any(kw in lower for kw in ("create", "make")):
                return "create_file"
            if any(kw in lower for kw in ("delete", "remove")):
                return "delete_file"
            return "system_generic"
        elif intent_type_str == "DEV_TASK":
            lower = text.lower()
            if "push" in lower:
                return "git_push"
            if "pull" in lower:
                return "git_pull"
            if "commit" in lower:
                return "git_commit"
            return "dev_generic"
        elif intent_type_str == "CODE_GENERATION":
            return "generate_code"
        elif intent_type_str == "VISION_TASK":
            return "vision_analyze"
        else:
            return "llm_respond"
