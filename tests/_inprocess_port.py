"""Test helper: an in-process :class:`WorkerPort` that wraps an
:class:`ExecutionEngine`.

Real production code uses :class:`aura.runtime.worker_client.WorkerClient`,
which talks to a subprocess.  Tests that want synchronous execution use
this port instead - it speaks the same request/reply envelope the
worker speaks, so :meth:`CommandRegistry._execute_safe` cannot tell
the difference.

Importantly, this class is NOT callable (no ``__call__``) so the
closure-walk invariant ("every cell in ``_execute_safe.__closure__`` is
non-callable or is the safe pipeline itself") holds when the registry
captures an :class:`InProcessWorkerPort` as a data reference.
"""
from __future__ import annotations

from typing import Any

from aura.core.errors import AuraError
from aura.core.event_bus import EventBus
from aura.core.result import CommandResult
from aura.runtime.command_registry import CommandRegistry
from aura.runtime.execution_engine import ExecutionEngine
from aura.security.plugin_manifest import PluginManifest


class InProcessWorkerPort:
    # ``__weakref__`` required so the registry's capability table
    # (module-level ``weakref.WeakValueDictionary``) can hold us.
    __slots__ = ("_engine", "_meta", "__weakref__")

    def __init__(self, engine: ExecutionEngine) -> None:
        self._engine = engine
        self._meta: dict[str, dict[str, Any]] = {}

    # Convenience so tests can mirror what plugin_loader does in prod.
    def register(
        self,
        action: str,
        executor,
        *,
        plugin_instance,
        plugin: str = "test",
        description: str = "",
        destructive: bool = False,
        permission_level: str = "MEDIUM",
    ) -> None:
        self._engine.register(
            action, executor, plugin_instance=plugin_instance
        )
        self._meta[action] = {
            "action": action,
            "plugin": plugin,
            "description": description,
            "destructive": bool(destructive),
            "permission_level": permission_level,
        }

    # ---- WorkerPort protocol -----------------------------------------
    def has(self, action: str) -> bool:
        return self._engine.has(action)

    def actions(self) -> list[dict[str, Any]]:
        return [dict(v) for v in self._meta.values()]

    def send(self, request: dict[str, Any]) -> dict[str, Any]:
        request_id = request.get("id")
        action = request.get("action")
        action_echo = action if isinstance(action, str) else None
        params = request.get("params") or {}
        if not isinstance(action, str) or not action.strip():
            return {
                "type": "error",
                "id": request_id,
                "action": action_echo,
                "error_class": "SchemaError",
                "error_code": "SCHEMA_ERROR",
                "message": "Missing or empty 'action'",
            }
        if not isinstance(params, dict):
            return {
                "type": "error",
                "id": request_id,
                "action": action_echo,
                "error_class": "SchemaError",
                "error_code": "SCHEMA_ERROR",
                "message": "'params' must be a dict",
            }
        try:
            result = self._engine.dispatch(action, dict(params))
        except AuraError as exc:
            return {
                "type": "error",
                "id": request_id,
                "action": action_echo,
                "error_class": type(exc).__name__,
                "error_code": getattr(exc, "code", None) or "EXECUTION_ERROR",
                "message": str(exc),
            }
        except Exception as exc:  # noqa: BLE001 - match worker boundary
            return {
                "type": "error",
                "id": request_id,
                "action": action_echo,
                "error_class": type(exc).__name__,
                "error_code": "EXECUTION_ERROR",
                "message": str(exc),
            }
        if not isinstance(result, CommandResult):
            return {
                "type": "error",
                "id": request_id,
                "action": action_echo,
                "error_class": "EngineError",
                "error_code": "ENGINE_ERROR",
                "message": "non-CommandResult returned by executor",
            }
        return {
            "type": "result",
            "id": request_id,
            "action": action_echo,
            "success": bool(result.success),
            "message": str(result.message),
            "data": dict(result.data or {}),
            "command_type": result.command_type or action,
            "error_code": result.error_code,
        }


def make_registry(
    bus: EventBus,
    engine: ExecutionEngine,
    *,
    manifest: PluginManifest | None = None,
    **kwargs,
) -> CommandRegistry:
    """Convenience: build a registry backed by an :class:`InProcessWorkerPort`
    wrapping ``engine``.  Exists purely so tests don't have to import
    :class:`InProcessWorkerPort` + :class:`CommandRegistry` separately.
    """
    port = InProcessWorkerPort(engine)
    return CommandRegistry(
        bus,
        port,
        manifest=manifest or PluginManifest.permissive(),
        **kwargs,
    )
