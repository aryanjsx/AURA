"""
AURA — Command Registry (LOCKED DOWN, single enforcement point).

After the Phase-2 lockdown the registry is the **only** reachable entry
point into the execution backend.  Key invariants:

1. There is exactly ONE execution path.  Nothing — not router, not
   planner, not a future LLM adapter, not a plugin — can reach the raw
   executor map, the engine, or the worker client.
2. The registry captures its dispatch capability via a one-shot
   ``_seal()`` call on the backend at construction time.  The backend
   object is NEVER stored on the registry; only the captured bound
   method (kept in a name-mangled slot) is retained.
3. Every :meth:`execute` call runs the full safety pipeline
   (schema → size → rate-limit → permission → safety-gate →
   lifecycle → dispatch → lifecycle) so security does not depend on
   caller discipline.
4. :meth:`register_metadata` authoritatively validates the plugin's
   self-declared flags against a :class:`PluginManifest`.  Without a
   manifest, registration fails hard.

Any future entry point (API, LLM, Bus) MUST go through
:meth:`execute` — there is no supported alternative.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from aura.core.errors import (
    AuraError,
    ConfirmationDenied,  # noqa: F401 — re-exported for callers
    ConfirmationTimeout,  # noqa: F401
    ExecutionError,
    PermissionDenied,
    RateLimitError,
    RegistryError,
    SchemaError,
)
from aura.core.event_bus import EventBus
from aura.core.param_schema import validate_params
from aura.security.permissions import PermissionLevel, PermissionValidator
from aura.security.plugin_manifest import PluginManifest, PluginManifestError
from aura.security.rate_limiter import RateLimiter
from aura.core.result import CommandResult
from aura.security.safety_gate import AutoConfirmGate, SafetyGate
from aura.core.schema import CommandSpec, validate_command
from aura.core.tracing import current_trace_id


class Sealable(Protocol):
    """Protocol for a dispatch backend that can be sealed exactly once.

    Both :class:`~aura.runtime.execution_engine.ExecutionEngine` and
    :class:`~aura.runtime.worker_client.WorkerClient` satisfy this protocol.
    """

    def _seal(self) -> Callable[[str, dict[str, Any]], CommandResult]: ...

    def has(self, action: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class CommandEntry:
    """Metadata for one registered action (NO callable stored)."""

    action: str
    plugin: str
    description: str = ""
    destructive: bool = False
    permission_level: PermissionLevel = PermissionLevel.MEDIUM


class CommandRegistry:
    """Metadata store + single safety-enforcing dispatch proxy."""

    def __init__(
        self,
        bus: EventBus,
        dispatcher_source: Sealable,
        *,
        manifest: PluginManifest | None = None,
        rate_limiter: RateLimiter | None = None,
        permission_validator: PermissionValidator | None = None,
        safety_gate: SafetyGate | None = None,
        auto_confirm: bool = False,
    ) -> None:
        self._bus = bus

        # Capture the dispatch capability once.  After this, there is
        # no path from the registry back to the engine/worker object.
        if not hasattr(dispatcher_source, "_seal"):
            raise RegistryError(
                "dispatcher_source must expose a one-shot _seal() capability"
            )
        dispatch_fn = dispatcher_source._seal()
        if not callable(dispatch_fn):
            raise RegistryError("dispatcher_source._seal() must return a callable")
        # Name-mangled — no public attribute exposes it.
        self.__dispatch: Callable[[str, dict[str, Any]], CommandResult] = dispatch_fn
        # We keep a ``has`` predicate only (never the object itself).
        self.__has: Callable[[str], bool] = dispatcher_source.has

        self._entries: dict[str, CommandEntry] = {}
        self._lock = threading.RLock()

        # Manifest — required by :meth:`register_metadata`.  A manifest
        # of ``None`` means the registry REFUSES to register any action.
        self._manifest: PluginManifest | None = manifest

        # Security components.  All have safe defaults so that any code
        # that forgets to call :meth:`attach_security` still gets a
        # working enforcement chain (rather than a bypassable stub).
        self._rate_limiter = rate_limiter or RateLimiter()
        self._permissions = permission_validator or PermissionValidator()
        self._auto_confirm = bool(auto_confirm)
        self._safety_gate: SafetyGate = safety_gate or AutoConfirmGate(bus)

    # ---- security wiring (used by Router/main.py) ---------------------
    def attach_security(
        self,
        *,
        rate_limiter: RateLimiter | None = None,
        permission_validator: PermissionValidator | None = None,
        safety_gate: SafetyGate | None = None,
        auto_confirm: bool | None = None,
    ) -> None:
        """Replace one or more security components after construction."""
        if rate_limiter is not None:
            self._rate_limiter = rate_limiter
        if permission_validator is not None:
            self._permissions = permission_validator
        if safety_gate is not None:
            self._safety_gate = safety_gate
        if auto_confirm is not None:
            self._auto_confirm = bool(auto_confirm)

    def attach_manifest(self, manifest: PluginManifest) -> None:
        """Install / replace the authoritative plugin manifest."""
        if not isinstance(manifest, PluginManifest):
            raise RegistryError("manifest must be a PluginManifest instance")
        self._manifest = manifest

    # ---- registration (called only by the plugin loader) --------------
    def register_metadata(
        self,
        action: str,
        *,
        plugin: str,
        description: str = "",
        destructive: bool = False,
        permission_level: PermissionLevel = PermissionLevel.MEDIUM,
    ) -> None:
        if not isinstance(action, str) or not action.strip():
            raise RegistryError("action must be a non-empty string")
        if not isinstance(plugin, str) or not plugin.strip():
            raise RegistryError("plugin name is required")
        level = PermissionLevel.parse(permission_level)
        clean_action = action.strip()
        clean_plugin = plugin.strip()

        # Authoritative manifest check — the registry does NOT trust the
        # plugin or the worker for permission_level / destructive flags.
        if self._manifest is None:
            raise RegistryError(
                "Cannot register metadata without an attached PluginManifest. "
                "Construct the registry with ``manifest=...`` or call "
                "``attach_manifest()`` first."
            )
        try:
            self._manifest.check(
                plugin=clean_plugin,
                action=clean_action,
                permission_level=level,
                destructive=bool(destructive),
            )
        except PluginManifestError as exc:
            raise RegistryError(
                f"Manifest rejected action {clean_action!r}: {exc}"
            ) from exc

        entry = CommandEntry(
            action=clean_action,
            plugin=clean_plugin,
            description=description or "",
            destructive=bool(destructive),
            permission_level=level,
        )

        with self._lock:
            if entry.action in self._entries:
                raise RegistryError(
                    f"Duplicate registration for action {entry.action!r} "
                    f"(existing plugin: {self._entries[entry.action].plugin})"
                )
            self._entries[entry.action] = entry

        self._bus.emit(
            "registry.registered",
            {
                "action": entry.action,
                "plugin": entry.plugin,
                "destructive": entry.destructive,
                "permission_level": entry.permission_level.value,
            },
        )

    def unregister(self, action: str) -> bool:
        with self._lock:
            removed = self._entries.pop(action, None)
        if removed is not None:
            self._bus.emit("registry.unregistered", {"action": action})
            return True
        return False

    # ---- lookup --------------------------------------------------------
    def has(self, action: str) -> bool:
        with self._lock:
            return action in self._entries

    def get(self, action: str) -> CommandEntry:
        with self._lock:
            entry = self._entries.get(action)
        if entry is None:
            raise RegistryError(f"Unknown action: {action!r}")
        return entry

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {
                    "action": e.action,
                    "plugin": e.plugin,
                    "description": e.description,
                    "destructive": e.destructive,
                    "permission_level": e.permission_level.value,
                }
                for e in self._entries.values()
            ]

    # ---- execution -----------------------------------------------------
    def execute(
        self,
        payload: Any,
        *,
        source: str = "auto",
    ) -> CommandResult:
        """Run the full safety pipeline, then dispatch.

        ``source`` defaults to ``"auto"`` (lowest-privilege cap) so that
        any code path which forgets to declare a source fails safely
        rather than silently inheriting CLI-level authority.
        """
        if not isinstance(source, str) or not source.strip():
            raise SchemaError("source must be a non-empty string")
        source = source.strip().lower()

        spec = payload if isinstance(payload, CommandSpec) else validate_command(payload)
        entry = self.get(spec.action)  # raises RegistryError on unknown

        trace_id = current_trace_id()

        # 1) Parameter schema + size limits.  Runs BEFORE logging/IPC so
        #    oversized payloads never touch the audit log.
        try:
            validate_params(entry.action, dict(spec.params))
        except SchemaError as exc:
            self._bus.emit(
                "schema.rejected",
                {
                    "action": entry.action,
                    "source": source,
                    "reason": str(exc),
                    "trace_id": trace_id,
                },
            )
            raise

        # 2) Rate limit (per-source sliding window + repeat guard).
        try:
            self._rate_limiter.check(
                entry.action, dict(spec.params), source=source
            )
        except RateLimitError as exc:
            self._bus.emit(
                "rate_limit.blocked",
                {
                    "action": entry.action,
                    "source": source,
                    "trace_id": trace_id,
                    "reason": str(exc),
                },
            )
            raise

        # 3) Permission check vs source cap.
        try:
            self._permissions.validate(
                action=entry.action,
                level=entry.permission_level,
                source=source,
            )
        except PermissionDenied as exc:
            self._bus.emit(
                "permission.denied",
                {
                    "action": entry.action,
                    "source": source,
                    "required": entry.permission_level.value,
                    "trace_id": trace_id,
                    "reason": str(exc),
                },
            )
            raise

        # 4) Safety gate (destructive commands OR explicitly opt-in).
        spec = self._apply_safety(spec, entry, source=source, trace_id=trace_id)

        # 5) Lifecycle: executing / destructive marker.
        self._bus.emit(
            "command.executing",
            {
                "action": entry.action,
                "plugin": entry.plugin,
                "destructive": entry.destructive,
                "permission_level": entry.permission_level.value,
                "requires_confirm": spec.requires_confirm,
                "source": source,
                "trace_id": trace_id,
            },
        )
        if entry.destructive:
            self._bus.emit(
                "command.destructive",
                {
                    "action": entry.action,
                    "source": source,
                    "permission_level": entry.permission_level.value,
                    "trace_id": trace_id,
                },
            )

        # 6) Dispatch through the sealed capability only.
        try:
            result = self.__dispatch(entry.action, dict(spec.params))
        except AuraError:
            raise
        except TypeError as exc:
            raise RegistryError(
                f"Invalid arguments for {entry.action!r}: {exc}"
            ) from exc
        except Exception as exc:  # noqa: BLE001 — engine/exec boundary
            raise ExecutionError(
                f"Handler {entry.action!r} raised {type(exc).__name__}: {exc}"
            ) from exc

        if not result.command_type:
            result.command_type = entry.action

        # 7) Completion lifecycle.
        self._bus.emit(
            "command.completed",
            {
                "action": entry.action,
                "success": result.success,
                "source": source,
                "trace_id": trace_id,
            },
        )
        return result

    # ------------------------------------------------------------------
    # Safety gate helper.
    # ------------------------------------------------------------------
    def _apply_safety(
        self,
        spec: CommandSpec,
        entry: CommandEntry,
        *,
        source: str,
        trace_id: str | None,
    ) -> CommandSpec:
        if entry.destructive and not spec.requires_confirm:
            spec = spec.with_confirm(True)
        if not spec.requires_confirm:
            return spec

        if self._auto_confirm:
            self._bus.emit(
                "command.auto_confirmed",
                {
                    "action": spec.action,
                    "source": source,
                    "trace_id": trace_id,
                },
            )
            return spec

        # Real safety gate: may raise ConfirmationDenied / ConfirmationTimeout.
        self._safety_gate.request(
            action=spec.action,
            params=dict(spec.params),
            source=source,
            permission=entry.permission_level.value,
            trace_id=trace_id,
        )
        return spec
