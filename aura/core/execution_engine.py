"""
AURA — Execution Engine (locked down).

The engine owns the only callable references to executors and is the
in-process counterpart of :class:`~aura.core.worker_client.WorkerClient`.

After Phase-2 lockdown, **no public dispatch method exists**.  The engine
exports its dispatch capability exactly once, via a one-shot
:meth:`_seal` method that :class:`CommandRegistry` consumes during its
own construction.  After sealing:

* the engine's dispatch is reachable only via Python's name-mangling
  (``_ExecutionEngine__dispatch``) — no attribute, method, or protocol
  surface exposes it.
* a second ``_seal()`` call raises :class:`RuntimeError` so an attacker
  cannot re-export the capability.

The registry keeps the captured callable in its own name-mangled slot
and never stores a reference to the engine object itself.
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
    """Private-by-construction executor dispatcher."""

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self.__executors: dict[str, Executor] = {}
        self.__plugin_refs: dict[str, Any] = {}
        self.__lock = threading.RLock()
        self.__sealed: bool = False

    # -- registration is only done by the plugin loader during bootstrap.
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
        with self.__lock:
            if action in self.__executors:
                raise EngineError(
                    f"Duplicate executor registration for {action!r}"
                )
            self.__executors[action] = executor
            self.__plugin_refs[action] = plugin_instance

    def has(self, action: str) -> bool:
        with self.__lock:
            return action in self.__executors

    def actions(self) -> list[str]:
        with self.__lock:
            return sorted(self.__executors.keys())

    # ------------------------------------------------------------------
    # Private dispatch — NEVER accessed directly from outside this class.
    # ------------------------------------------------------------------
    def __dispatch(self, action: str, params: dict[str, Any]) -> CommandResult:
        with self.__lock:
            executor = self.__executors.get(action)
        if executor is None:
            raise RegistryError(f"No executor registered for action: {action!r}")

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

    # ------------------------------------------------------------------
    # One-shot capability export — consumed by CommandRegistry.__init__
    # ------------------------------------------------------------------
    def _seal(self) -> Callable[[str, dict[str, Any]], CommandResult]:
        """Hand the dispatch capability to the CommandRegistry.

        After the first call, further attempts raise ``RuntimeError``.
        The returned bound method is the ONLY reachable path to
        ``__dispatch`` from outside this class.
        """
        if self.__sealed:
            raise RuntimeError(
                "ExecutionEngine has already been sealed; dispatch is private."
            )
        self.__sealed = True
        return self.__dispatch  # bound method — captures self

    @property
    def sealed(self) -> bool:
        return self.__sealed

    # -- Internal inspection hook for tests; not part of the public API.
    def _size(self) -> int:
        with self.__lock:
            return len(self.__executors)
