# aura/core/safety_gate.py
# AURA Safety Gate — ALL destructive operations MUST pass through here.
#
# NON-NEGOTIABLE RULES (from Engineering Spec §5):
#   - NEVER bypass this gate for destructive commands
#   - Only "yes", "confirm", "do it", "proceed" are valid confirmations
#   - Confirmation window is exactly safety.confirmation_timeout seconds (default 8)
#   - Every decision — confirmed OR denied — is appended to safety_audit.log
#   - If confirmation times out → DENY (fail-safe)
#   - eval() and exec() are permanently banned

from __future__ import annotations
import logging
import os
import queue
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from aura.schemas.command import CommandPlan, ExecutionResult, ExecutorType
from aura.core.event_bus import bus, EventType

logger = logging.getLogger("aura.safety_gate")

# Words that count as voice confirmation — lowercase, stripped
_CONFIRM_WORDS: frozenset[str] = frozenset({"yes", "confirm", "do it", "proceed"})


class SafetyGate:
    """
    Intercepts destructive CommandPlans and requests voice confirmation
    before allowing execution to proceed.

    Usage:
        gate = SafetyGate(config)
        approved: bool = gate.check(command_plan)
        if approved:
            executor.run(command_plan)
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self._timeout: int = int(
            config.get("safety", {}).get("confirmation_timeout", 8)
        )
        audit_path: str = config.get("safety", {}).get(
            "audit_log", "logs/safety_audit.log"
        )
        self._audit_log = Path(audit_path)
        self._audit_log.parent.mkdir(parents=True, exist_ok=True)

        # Queue used to receive voice responses from the STT layer
        # The STTEngine should call safety_gate.receive_confirmation(text)
        # after it detects a response during AWAITING_CONFIRM state
        self._response_queue: queue.Queue[str] = queue.Queue()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check(self, plan: CommandPlan) -> bool:
        """
        Main entry point.
        Returns True  → safe to proceed
        Returns False → command must be CANCELLED
        """
        if not plan.is_destructive and not plan.requires_confirm:
            return True   # Non-destructive commands pass through immediately

        prompt = self._build_prompt(plan)
        logger.info(f"SafetyGate blocking: {plan.executor.name}.{plan.action}")

        # 1. Ask for confirmation via TTS + GUI
        bus.emit(EventType.SAFETY_CONFIRMATION_REQ, {
            "prompt_text": prompt,
            "command": {
                "executor": plan.executor.name,
                "action": plan.action,
                "params": plan.params,
            },
        })

        # 2. Wait for voice response
        confirmed = self._await_confirmation(plan)

        # 3. Emit result event
        if confirmed:
            bus.emit(EventType.SAFETY_CONFIRMED, {
                "command": plan.action,
                "timestamp": datetime.now().isoformat(),
            })
        else:
            bus.emit(EventType.SAFETY_DENIED, {
                "command": plan.action,
                "reason": "User did not confirm or timed out",
            })

        # 4. Write to audit log — always, regardless of outcome
        self._write_audit(plan, confirmed)

        return confirmed

    def receive_confirmation(self, spoken_text: str) -> None:
        """
        Called by the STTEngine when it captures a voice response
        during the AWAITING_CONFIRM pipeline state.
        Non-blocking — puts result into internal queue.
        """
        self._response_queue.put(spoken_text.strip().lower())

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _await_confirmation(self, plan: CommandPlan) -> bool:
        """Block for up to self._timeout seconds waiting for voice input."""
        try:
            response = self._response_queue.get(timeout=self._timeout)
        except queue.Empty:
            logger.warning(
                f"SafetyGate: confirmation timed out after {self._timeout}s "
                f"for {plan.executor.name}.{plan.action}"
            )
            return False

        # Normalise: strip punctuation, lowercase
        cleaned = "".join(c for c in response if c.isalpha() or c.isspace()).strip()
        approved = cleaned in _CONFIRM_WORDS
        logger.info(
            f"SafetyGate: response='{cleaned}' → {'CONFIRMED' if approved else 'DENIED'}"
        )
        return approved

    def _build_prompt(self, plan: CommandPlan) -> str:
        """
        Return the exact TTS string AURA will speak to ask for confirmation.
        Matches the prompts defined in Engineering Spec §5.1.
        """
        p = plan.params
        action = plan.action
        executor = plan.executor

        # --- File operations ---
        if executor == ExecutorType.SYSTEM and action == "shutdown":
            return "I'm about to shut down your computer. Say yes to confirm."
        if executor == ExecutorType.SYSTEM and action == "restart":
            return "I'm about to restart your computer. Say yes to confirm."
        if executor == ExecutorType.SYSTEM and action == "kill_process":
            name = p.get("process_name", "unknown")
            pid  = p.get("pid", "")
            pid_str = f" (PID {pid})" if pid else ""
            return f"Killing process {name}{pid_str}. Confirm?"
        if executor == ExecutorType.SYSTEM and action == "log_off":
            return "I'm about to log off your current user session. Say yes to confirm."

        # --- Shell ---
        if executor == ExecutorType.SHELL and action == "run_command":
            cmd = p.get("command", "unknown command")
            return f"I'm about to run: {cmd}. Say yes to confirm."

        # --- Generic fallback ---
        return (
            f"I'm about to perform {executor.name} action {action}. "
            f"Say yes to confirm, or stay silent to cancel."
        )

    def _write_audit(self, plan: CommandPlan, confirmed: bool) -> None:
        """Append one line to the safety audit log."""
        outcome = "CONFIRMED" if confirmed else "DENIED"
        entry = (
            f"{datetime.now().isoformat()} | {outcome} | "
            f"{plan.executor.name}.{plan.action} | "
            f"params={plan.params}\n"
        )
        try:
            with self._audit_log.open("a", encoding="utf-8") as f:
                f.write(entry)
        except OSError as exc:
            logger.error(f"SafetyGate: could not write audit log: {exc}")
