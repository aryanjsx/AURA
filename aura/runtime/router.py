"""
AURA — Router (narrative layer).

With Phase-2 hardening, the **entire safety pipeline** (rate limit,
permission, schema+size validation, safety gate, lifecycle emission)
lives inside :class:`~aura.runtime.command_registry.CommandRegistry`.

The router is now a thin narrative wrapper:

    text / intent
        ↓
    parse → CommandSpec       (Router)
        ↓
    allocate trace_id         (Router: TraceScope)
        ↓
    Registry.execute(spec, source=...)    ← safety pipeline runs here
        ↓
    CommandResult

Security is no longer split across router + registry, so a direct caller
to the registry cannot bypass a check by "forgetting" to go through the
router.
"""

from __future__ import annotations

from typing import Any

from aura.runtime.command_registry import CommandRegistry
from aura.core.error_handler import handle_error
from aura.core.errors import RegistryError, SchemaError
from aura.core.event_bus import EventBus
from aura.core.intent import Intent
from aura.core.logger import benchmark, get_logger, trace
from aura.security.permissions import PermissionValidator
from aura.core.plugin_base import IntentParser
from aura.security.rate_limiter import RateLimiter
from aura.core.result import CommandResult
from aura.security.safety_gate import AutoConfirmGate, SafetyGate
from aura.core.schema import CommandSpec, intent_to_spec, validate_command
from aura.core.tracing import TraceScope, current_trace_id

logger = get_logger("aura.router")


class Router:
    """Text / Intent → CommandSpec → CommandRegistry (which enforces safety)."""

    def __init__(
        self,
        bus: EventBus,
        registry: CommandRegistry,
        intent_parsers: list[IntentParser] | None = None,
        *,
        safety_gate: SafetyGate | None = None,
        permission_validator: PermissionValidator | None = None,
        rate_limiter: RateLimiter | None = None,
        auto_confirm: bool = False,
    ) -> None:
        self._bus = bus
        self._registry = registry
        self._parsers: list[IntentParser] = list(intent_parsers or [])
        self._auto_confirm = bool(auto_confirm)

        # Forward the security components straight into the registry so
        # there is exactly ONE enforcement site.  Defaulting to real
        # instances here (rather than ``None``) preserves the previous
        # Router constructor contract for tests that don't provide them.
        gate: SafetyGate = safety_gate or (
            AutoConfirmGate(bus) if self._auto_confirm else SafetyGate(bus)
        )
        self._registry.attach_security(
            rate_limiter=rate_limiter or RateLimiter(),
            permission_validator=permission_validator or PermissionValidator(),
            safety_gate=gate,
            auto_confirm=self._auto_confirm,
        )

    def add_parser(self, parser: IntentParser) -> None:
        if not callable(parser):
            raise TypeError("parser must be callable")
        self._parsers.append(parser)

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------
    def route(self, text: str, *, source: str = "cli") -> CommandResult:
        """Parse *text* and execute through the registry's pipeline."""
        with TraceScope() as scope, benchmark(
            logger, "router.route", text=text or "", trace_id=scope.trace_id,
            source=source,
        ):
            self._bus.emit(
                "command.received",
                {"text": text, "source": source, "trace_id": scope.trace_id},
            )

            if not text or not text.strip():
                return handle_error(
                    SchemaError("Empty command"),
                    bus=self._bus,
                    context={"text": text, "source": source,
                             "trace_id": scope.trace_id},
                )

            try:
                intent = self._parse(text)
                trace(logger, "intent.parsed",
                      action=intent.action, args=intent.args,
                      trace_id=scope.trace_id)
                self._bus.emit(
                    "intent.parsed",
                    {
                        "action": intent.action,
                        "args": intent.args,
                        "source": source,
                        "trace_id": scope.trace_id,
                    },
                )
                return self._registry.execute(
                    intent_to_spec(intent),
                    source=source,
                )
            except Exception as exc:  # noqa: BLE001
                return handle_error(
                    exc,
                    bus=self._bus,
                    context={"text": text, "source": source,
                             "trace_id": scope.trace_id},
                )

    def execute_intent(
        self,
        intent: Intent,
        *,
        source: str,
    ) -> CommandResult:
        """Execute a pre-built intent.

        ``source`` is a REQUIRED keyword argument — callers must declare
        whether the intent came from ``"llm"``, ``"api"``, ``"cli"``,
        etc.  The registry uses *that* value, not anything carried on
        the intent itself (intents no longer carry a source field).
        """
        if not isinstance(source, str) or not source.strip():
            raise SchemaError(
                "execute_intent requires a non-empty 'source' keyword argument"
            )
        clean_source = source.strip().lower()
        with TraceScope() as scope:
            try:
                return self._registry.execute(
                    intent_to_spec(intent),
                    source=clean_source,
                )
            except Exception as exc:  # noqa: BLE001
                return handle_error(
                    exc,
                    bus=self._bus,
                    context={"source": clean_source, "action": intent.action,
                             "trace_id": scope.trace_id},
                )

    def execute_action(
        self,
        action: str,
        params: dict[str, Any] | None = None,
        *,
        source: str = "cli",
    ) -> CommandResult:
        """Programmatic entry point (used by the Task Planner)."""
        if current_trace_id() is None:
            with TraceScope():
                return self._execute_programmatic(action, params or {}, source)
        return self._execute_programmatic(action, params or {}, source)

    def _execute_programmatic(
        self, action: str, params: dict[str, Any], source: str
    ) -> CommandResult:
        try:
            spec = validate_command(
                {"action": action, "params": params, "requires_confirm": False}
            )
            return self._registry.execute(spec, source=source)
        except Exception as exc:  # noqa: BLE001
            return handle_error(
                exc,
                bus=self._bus,
                context={"action": action, "source": source,
                         "trace_id": current_trace_id()},
            )

    # ------------------------------------------------------------------
    # Intent parsing
    # ------------------------------------------------------------------
    def _parse(self, text: str) -> Intent:
        for parser in self._parsers:
            try:
                result = parser(text)
            except Exception as exc:
                logger.warning(
                    "parser.failed",
                    extra={
                        "event": "parser.failed",
                        "data": {"parser": getattr(parser, "__name__", "?"),
                                 "error": str(exc)},
                    },
                )
                continue
            if result is None:
                continue
            if not isinstance(result, Intent):
                raise RegistryError(
                    f"Intent parser returned {type(result).__name__}, expected Intent"
                )
            # Re-wrap to attach raw text.  Intent has NO ``source`` — the
            # caller of route()/execute_intent() owns that fact.
            return Intent(
                action=result.action,
                args=result.args,
                raw_text=text,
                confidence=result.confidence,
                requires_confirm=result.requires_confirm,
            )
        raise RegistryError(f"Unknown command: {text!r}")
