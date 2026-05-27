"""
AURA — Command Engine (Phase 2).

Receives a CommandPlan from BrainController, validates it through
SafetyGate if destructive, routes to the appropriate executor, and
returns an ExecutionResult.

Events emitted:
  EXECUTION_STARTED  — { executor, action }
  EXECUTION_COMPLETE — { result: ExecutionResult }
"""

from __future__ import annotations

import logging
import time
from typing import Any

from aura.core.schemas import CommandPlan, ExecutionResult

logger = logging.getLogger("aura.command_engine")


class CommandEngine:
    """Routes CommandPlans to executors and manages execution lifecycle."""

    def __init__(self, config: dict[str, Any], event_bus: Any, safety_gate: Any) -> None:
        self._config = config
        self._event_bus = event_bus
        self._safety_gate = safety_gate

    def execute(self, command_plan: CommandPlan) -> ExecutionResult:
        """Execute a command plan, emitting lifecycle events.

        Parameters
        ----------
        command_plan : CommandPlan
            Plan from BrainController.handle_intent().

        Returns
        -------
        ExecutionResult
            Result with success/output/error fields.
        """
        from aura.core.event_bus import EventType

        self._event_bus.emit(EventType.EXECUTION_STARTED, {
            "executor": command_plan.executor,
            "action": command_plan.action,
        })

        start = time.perf_counter()

        # Safety gate check for destructive operations
        was_confirmed = False
        if command_plan.is_destructive:
            try:
                confirmed = self._safety_gate.check(command_plan)
                if not confirmed:
                    result = ExecutionResult(
                        success=False,
                        output="Action cancelled — confirmation was denied.",
                        error="Safety gate denied",
                        executor=command_plan.executor,
                        duration_ms=int((time.perf_counter() - start) * 1000),
                        was_confirmed=False,
                    )
                    self._event_bus.emit(EventType.EXECUTION_COMPLETE, {"result": result})
                    return result
                was_confirmed = True
            except Exception as exc:
                logger.error("Safety gate error: %s", exc)
                result = ExecutionResult(
                    success=False,
                    output="Action cancelled due to a safety check error.",
                    error=str(exc),
                    executor=command_plan.executor,
                    duration_ms=int((time.perf_counter() - start) * 1000),
                    was_confirmed=False,
                )
                self._event_bus.emit(EventType.EXECUTION_COMPLETE, {"result": result})
                return result

        # Route to executor
        try:
            result = self._route_to_executor(command_plan)
            result.was_confirmed = was_confirmed
        except Exception as exc:
            logger.exception("Executor failed: %s", exc)
            result = ExecutionResult(
                success=False,
                output=f"Execution failed: {exc}",
                error=str(exc),
                executor=command_plan.executor,
                duration_ms=int((time.perf_counter() - start) * 1000),
                was_confirmed=was_confirmed,
            )

        result.duration_ms = int((time.perf_counter() - start) * 1000)
        self._event_bus.emit(EventType.EXECUTION_COMPLETE, {"result": result})
        return result

    def _route_to_executor(self, plan: CommandPlan) -> ExecutionResult:
        """Dispatch to the correct executor based on plan.executor."""
        executor = plan.executor.upper()

        if executor == "SYSTEM":
            return self._execute_system(plan)
        elif executor in ("GIT", "DOCKER", "NPM", "SHELL"):
            return self._execute_shell(plan)
        elif executor == "VISION":
            return ExecutionResult(
                success=False,
                output="Vision tasks are available from Phase 4.",
                executor=plan.executor,
            )
        elif executor == "BROWSER":
            return ExecutionResult(
                success=False,
                output="Browser tasks are not yet implemented.",
                executor=plan.executor,
            )
        elif executor == "LLM_ONLY":
            return self._execute_llm_only(plan)
        else:
            return ExecutionResult(
                success=False,
                output=f"Unknown executor: {plan.executor}",
                error=f"No handler for executor '{plan.executor}'",
                executor=plan.executor,
            )

    def _execute_system(self, plan: CommandPlan) -> ExecutionResult:
        """Execute system commands (app launch, stats, file ops)."""
        from aura.core.voice_executor import execute as execute_voice_command

        result_text = execute_voice_command(plan.params.get("raw_text", plan.params.get("prompt", "")))

        if result_text:
            return ExecutionResult(
                success=True,
                output=result_text,
                data={"raw_output": result_text},
                executor=plan.executor,
            )

        # System executor returned nothing — fall back to LLM
        return self._execute_llm_only(plan)

    def _execute_shell(self, plan: CommandPlan) -> ExecutionResult:
        """Execute shell/git/docker/npm commands.

        Pending full integration — currently returns a status message.
        """
        return ExecutionResult(
            success=True,
            output=f"Dev task recognized: {plan.action}. "
                   "Full shell execution is pending Phase 3 integration.",
            executor=plan.executor,
        )

    def _execute_llm_only(self, plan: CommandPlan) -> ExecutionResult:
        """Mark as LLM-only — the caller (main.py pipeline) handles streaming."""
        return ExecutionResult(
            success=True,
            output="",  # empty signals caller to stream from LLM
            data={
                "mode": "llm_stream",
                "model": plan.params.get("model", ""),
                "prompt": plan.params.get("prompt", ""),
            },
            executor=plan.executor,
        )
