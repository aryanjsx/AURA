"""
AURA — Dynamic Audit Event Registry.

Replaces the old hard-coded ``_AUDIT_EVENTS`` tuple with a *registry* that
plugins may extend at load time.  The registry also tracks which events
cover which actions so the plugin loader can refuse to register a
destructive command that has no audit coverage.

Design constraints
------------------
* Thread-safe (plugin loading may race with early-boot bus subscriptions).
* Append-only: events cannot be unregistered — removal would create
  silent gaps in the tamper-evident log.
* Global singleton available via :func:`get_audit_event_registry` so
  the :class:`~aura.core.audit_log.AuditLogger` and the plugin loader
  see the same view.
"""

from __future__ import annotations

import threading
from typing import Iterable


# Core events AURA itself emits.  These are always registered and
# can never be removed.
_CORE_EVENTS: tuple[str, ...] = (
    "confirmation.requested",
    "confirmation.accepted",
    "confirmation.denied",
    "confirmation.timeout",
    "permission.denied",
    "rate_limit.blocked",
    "policy.blocked",
    "sandbox.blocked",
    "schema.rejected",
    "command.destructive",
    "command.error",
    "command.executing",
    "command.completed",
    "plan.started",
    "plan.completed",
    "plan.rollback",
    "plan.failed",
    "plan.step.started",
    "plan.step.completed",
    "worker.ready",
    "worker.crashed",
    "worker.shutdown",
)


class AuditCoverageError(Exception):
    """Raised when a destructive action has no audit event coverage."""


class AuditEventRegistry:
    """Registry of audit event names + per-action coverage mapping."""

    def __init__(self, *, core_events: Iterable[str] = _CORE_EVENTS) -> None:
        self._lock = threading.RLock()
        self._events: set[str] = set()
        # action -> set[event_name]
        self._coverage: dict[str, set[str]] = {}
        for ev in core_events:
            self._register_event_unlocked(ev)

    # ------------------------------------------------------------------
    # event registration
    # ------------------------------------------------------------------
    def _register_event_unlocked(self, event: str) -> None:
        if not isinstance(event, str) or not event.strip():
            raise ValueError(f"audit event name must be non-empty str, got {event!r}")
        self._events.add(event.strip())

    def register_event(self, event: str) -> None:
        """Register a new audit event type (idempotent)."""
        with self._lock:
            self._register_event_unlocked(event)

    def events(self) -> frozenset[str]:
        """Snapshot of every currently-registered event name."""
        with self._lock:
            return frozenset(self._events)

    # ------------------------------------------------------------------
    # per-action coverage
    # ------------------------------------------------------------------
    def register_action_coverage(
        self, action: str, events: Iterable[str]
    ) -> None:
        """Declare which audit events cover *action*.

        All *events* are implicitly registered.  Intended to be called by
        the plugin loader while processing the manifest.
        """
        if not isinstance(action, str) or not action.strip():
            raise ValueError(f"action must be non-empty str, got {action!r}")
        action = action.strip()
        ev_list = [e for e in events if isinstance(e, str) and e.strip()]
        with self._lock:
            for e in ev_list:
                self._register_event_unlocked(e)
            bucket = self._coverage.setdefault(action, set())
            bucket.update(e.strip() for e in ev_list)

    def coverage_for(self, action: str) -> frozenset[str]:
        with self._lock:
            return frozenset(self._coverage.get(action, set()))

    def has_coverage(self, action: str) -> bool:
        with self._lock:
            return bool(self._coverage.get(action))

    def require_coverage(self, action: str) -> None:
        """Raise :class:`AuditCoverageError` if *action* has no coverage."""
        if not self.has_coverage(action):
            raise AuditCoverageError(
                f"Destructive action {action!r} has no audit event coverage. "
                f"Declare at least one `audit_events` entry in the manifest."
            )


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------
_singleton: AuditEventRegistry | None = None
_singleton_lock = threading.Lock()


def get_audit_event_registry() -> AuditEventRegistry:
    global _singleton
    with _singleton_lock:
        if _singleton is None:
            _singleton = AuditEventRegistry()
        return _singleton


def reset_audit_event_registry() -> None:
    """Test-only hook: clear the singleton so a fresh registry is built."""
    global _singleton
    with _singleton_lock:
        _singleton = None
