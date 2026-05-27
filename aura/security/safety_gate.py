"""
AURA — Safety Gate (Voice-based confirmation).

Blocks execution of a destructive command until the user vocally confirms.
Uses TTS to speak the confirmation prompt and STT to listen for the response.

Accepted tokens (case-insensitive): "yes", "confirm", "do it", "proceed".
Any other response, silence, or timeout → returns False (cancel).

All decisions are audit-logged.
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("aura.safety_gate")


# Destructive-action-specific TTS prompts
_CONFIRMATION_PROMPTS: dict[str, str] = {
    "delete_file":       "I'm about to delete {filename}. Say yes to confirm.",
    "rmdir":             "This will permanently delete the folder {name} and all contents. Confirm?",
    "delete_folder":     "This will permanently delete the folder {name} and all contents. Confirm?",
    "git_push":          "Pushing commits to {branch} on {remote}. Confirm?",
    "git_reset_hard":    "Hard reset will discard all uncommitted changes. This cannot be undone. Confirm?",
    "git_branch_delete": "Deleting branch {name}. Confirm?",
    "git_force_push":    "Force push to {branch} will overwrite remote history. Are you absolutely sure?",
    "docker_remove":     "Removing container {name} and its data. Confirm?",
    "docker_prune":      "System prune removes all stopped containers and unused images. Confirm?",
    "kill_process":      "Killing process {name}. Confirm?",
}

ACCEPTED_RESPONSES: frozenset[str] = frozenset({"yes", "confirm", "do it", "proceed"})


class SafetyGate:
    """Voice-based confirmation gate with audit logging."""

    def __init__(
        self,
        bus: Any,
        *,
        tts_engine: Any = None,
        stt_engine: Any = None,
        config: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> None:
        self._bus = bus
        self._tts = tts_engine
        self._stt = stt_engine

        # Read timeout from config
        safety_cfg = (config or {}).get("safety", {})
        configured_timeout = timeout or safety_cfg.get(
            "confirmation_timeout", safety_cfg.get("confirm_timeout", 8)
        )
        self._timeout = max(1.0, float(configured_timeout))

        # Audit log path from config
        self._audit_log_path = safety_cfg.get("audit_log", "logs/safety_audit.log")
        self._ensure_audit_dir()

    def _ensure_audit_dir(self) -> None:
        """Create the audit log directory if it does not exist."""
        try:
            Path(self._audit_log_path).parent.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            logger.warning("Could not create audit log directory: %s", exc)

    def check(self, command_plan: Any) -> bool:
        """Check whether the user confirms a destructive action.

        Parameters
        ----------
        command_plan : CommandPlan
            The plan to confirm.

        Returns
        -------
        bool
            True if confirmed, False if denied/timeout.
        """
        from aura.core.event_bus import EventType

        action = command_plan.action
        params = command_plan.params
        executor = command_plan.executor

        # Build the confirmation prompt
        prompt_template = _CONFIRMATION_PROMPTS.get(action)
        if prompt_template:
            try:
                prompt_text = prompt_template.format(**params)
            except KeyError:
                prompt_text = prompt_template.format_map(
                    {k: params.get(k, "unknown") for k in
                     ("filename", "name", "branch", "remote", "N")}
                )
        else:
            prompt_text = (
                f"I'm about to execute {action}. This action is destructive. "
                "Say yes to confirm."
            )

        # Emit safety confirmation request event
        self._bus.emit(EventType.SAFETY_CONFIRMATION_REQ, {
            "action": action,
            "executor": executor,
            "timeout_seconds": self._timeout,
        })

        # Speak the prompt via TTS
        if self._tts:
            self._tts.speak(prompt_text, priority=True)
            self._tts.wait_until_idle(timeout=30)
        else:
            print(f"[SAFETY] {prompt_text}")

        # Listen for voice response via STT
        response_text = ""
        if self._stt:
            try:
                result = self._stt.listen_and_transcribe()
                response_text = result.text.strip().lower() if result.text else ""
            except Exception as exc:
                logger.error("STT failed during safety check: %s", exc)
                response_text = ""
        else:
            # Fallback to stdin if no STT available
            try:
                import sys
                sys.stdout.write(f"[SAFETY] {prompt_text}\n> ")
                sys.stdout.flush()
                response_text = input().strip().lower()
            except Exception:
                response_text = ""

        # Check response
        confirmed = response_text in ACCEPTED_RESPONSES
        reason = "user_confirmed" if confirmed else f"denied (response: {response_text!r})"
        if not response_text:
            reason = "timeout"

        # Audit log
        self._audit_log(
            "CONFIRMED" if confirmed else "CANCELLED",
            executor=executor,
            action=action,
            params=params,
            reason=reason,
        )

        # Emit result event
        if confirmed:
            self._bus.emit(EventType.SAFETY_CONFIRMED, {
                "action": action, "executor": executor,
            })
        else:
            self._bus.emit(EventType.SAFETY_DENIED, {
                "action": action, "executor": executor, "reason": reason,
            })

        return confirmed

    def _audit_log(
        self,
        decision: str,
        *,
        executor: str,
        action: str,
        params: dict[str, Any],
        reason: str = "",
    ) -> None:
        """Write one audit line to the log file."""
        timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

        if decision == "CONFIRMED":
            line = f"{timestamp} | CONFIRMED | executor={executor} action={action} params={params}\n"
        else:
            line = f"{timestamp} | CANCELLED | executor={executor} action={action} reason={reason}\n"

        try:
            with open(self._audit_log_path, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception as exc:
            logger.error("Audit log write failed: %s", exc)

        logger.info("SafetyGate %s: %s %s", decision, action, reason)


class AutoConfirmGate(SafetyGate):
    """Silent gate that approves every request (tests / ``--yes`` only)."""

    def check(self, command_plan: Any) -> bool:
        self._audit_log(
            "CONFIRMED",
            executor=getattr(command_plan, "executor", "unknown"),
            action=getattr(command_plan, "action", "unknown"),
            params=getattr(command_plan, "params", {}),
            reason="auto_confirm",
        )
        return True
