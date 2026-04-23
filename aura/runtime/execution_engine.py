"""
AURA - Execution Engine (worker-side only).

Post Phase-3 lockdown invariants
--------------------------------
* The engine is instantiated **only inside the worker subprocess**.
  The main process never imports plugins and never owns an
  :class:`ExecutionEngine` - it talks to the worker exclusively via
  :class:`~aura.runtime.worker_client.WorkerClient` / the
  :class:`WorkerPort` protocol.
* There is no capability token, no ``_acquire_capability``, no
  ``_engine_dispatch`` closure, no "one-shot" exposure of a raw
  dispatcher function.  Inside the trusted worker, the IPC loop simply
  calls :meth:`dispatch` directly.
* A closure walk on the main-process registry can no longer find any
  function that reaches an executor, because executors live only here,
  and this module is only imported by the worker.

Security model
--------------
The engine is NOT a security boundary.  It is the worker's executor
dispatcher.  All security (validation, permission, rate-limit, safety
gate, audit) is enforced by the :class:`CommandRegistry`'s
``_execute_safe`` pipeline in the **main** process BEFORE the worker
ever sees the request.  The worker additionally re-validates param
schema + sandbox + policy as defence in depth (see ``aura/worker/server.py``).
"""
from __future__ import annotations

import threading
from typing import Any, Callable

from aura.core.errors import EngineError, RegistryError
from aura.core.event_bus import EventBus
from aura.core.logger import benchmark, get_logger
from aura.core.result import CommandResult
from aura.core.tracing import current_trace_id

Executor = Callable[..., CommandResult]

_logger = get_logger("aura.engine")


class ExecutionEngine:
    """Plugin executor table + dispatch entry point (worker-side only)."""

    __slots__ = (
        "_bus",
        "_executors",
        "_plugin_refs",
        "_lock",
    )

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._executors: dict[str, Executor] = {}
        self._plugin_refs: dict[str, Any] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Plugin registration (called by the worker's plugin loader).
    # ------------------------------------------------------------------
    def register(
        self,
        action: str,
        executor: Executor,
        *,
        plugin_instance: Any,
    ) -> None:
        if not isinstance(action, str) or not action.strip():
            raise EngineError("action must be a non-empty string")
        if not callable(executor):
            raise EngineError(f"executor for {action!r} must be callable")
        with self._lock:
            if action in self._executors:
                raise EngineError(
                    f"Duplicate executor registration for {action!r}"
                )
            self._executors[action] = executor
            self._plugin_refs[action] = plugin_instance

    def has(self, action: str) -> bool:
        with self._lock:
            return action in self._executors

    def actions(self) -> list[str]:
        with self._lock:
            return sorted(self._executors.keys())

    # ------------------------------------------------------------------
    # Dispatch.  This is called by the worker IPC loop (in-process,
    # inside the trusted worker subprocess).  It is NEVER called from
    # the main process.
    # ------------------------------------------------------------------
    def dispatch(
        self, action: str, params: dict[str, Any]
    ) -> CommandResult:
        with self._lock:
            executor = self._executors.get(action)
        if executor is None:
            raise RegistryError(
                f"No executor registered for action: {action!r}"
            )
        trace_id = current_trace_id()
        with benchmark(
            _logger,
            "engine.dispatch",
            action=action,
            trace_id=trace_id,
        ):
            result = executor(**params)
        if not isinstance(result, CommandResult):
            raise EngineError(
                f"Executor for {action!r} must return CommandResult, "
                f"got {type(result).__name__}"
            )
        return result

    # Tests-only.
    def _size(self) -> int:
        with self._lock:
            return len(self._executors)
