"""
Phase-2 hardening: the CommandRegistry is the single enforcement point.

These tests call :meth:`CommandRegistry.execute` *directly*, bypassing
the Router, and confirm that every security check (rate limit,
permission, schema, safety gate) still fires.  Security must NOT depend
on callers going through the Router.
"""
from __future__ import annotations

import pytest

from aura.runtime.command_registry import CommandRegistry
from aura.core.errors import (
    ConfirmationDenied,
    PermissionDenied,
    RateLimitError,
    SchemaError,
)
from aura.core.event_bus import EventBus
from aura.runtime.execution_engine import ExecutionEngine
from aura.security.permissions import PermissionLevel, PermissionValidator
from aura.security.plugin_manifest import PluginManifest
from aura.security.rate_limiter import RateLimiter
from aura.core.result import CommandResult
from aura.security.safety_gate import SafetyGate
from aura.core.schema import CommandSpec


def _build(*, auto_confirm: bool = True):
    bus = EventBus()
    engine = ExecutionEngine(bus)
    registry = CommandRegistry(
        bus, engine,
        manifest=PluginManifest.permissive(),
        auto_confirm=auto_confirm,
    )

    class _Owner:
        pass

    owner = _Owner()

    def _ok(**kwargs):
        return CommandResult(success=True, message="ok", data=dict(kwargs))

    engine.register("probe.low", _ok, plugin_instance=owner)
    engine.register("probe.high", _ok, plugin_instance=owner)
    engine.register("probe.destructive", _ok, plugin_instance=owner)

    registry.register_metadata(
        "probe.low", plugin="t", permission_level=PermissionLevel.LOW
    )
    registry.register_metadata(
        "probe.high", plugin="t", permission_level=PermissionLevel.HIGH
    )
    registry.register_metadata(
        "probe.destructive",
        plugin="t",
        permission_level=PermissionLevel.HIGH,
        destructive=True,
    )
    return bus, registry


def _spec(action: str, params: dict | None = None, confirm: bool = False) -> CommandSpec:
    return CommandSpec(action=action, params=params or {}, requires_confirm=confirm)


# ------------------------------------------------------------------
# Rate limit is enforced at the registry
# ------------------------------------------------------------------
def test_registry_enforces_rate_limit():
    bus, registry = _build()
    registry.attach_security(
        rate_limiter=RateLimiter(max_per_minute=1, repeat_threshold=1000)
    )
    registry.execute(_spec("probe.low"), source="cli")
    with pytest.raises(RateLimitError):
        registry.execute(_spec("probe.low"), source="cli")


# ------------------------------------------------------------------
# Per-source rate-limit isolation (cli cap !== llm cap)
# ------------------------------------------------------------------
def test_registry_rate_limits_are_per_source():
    bus, registry = _build()
    registry.attach_security(
        rate_limiter=RateLimiter(max_per_minute=1, repeat_threshold=1000)
    )
    registry.execute(_spec("probe.low"), source="cli")
    # Different source → independent bucket → still allowed.
    registry.execute(_spec("probe.low"), source="llm")


# ------------------------------------------------------------------
# Permission validation is enforced at the registry
# ------------------------------------------------------------------
def test_registry_enforces_permissions_against_source_cap():
    bus, registry = _build()
    # llm is capped at MEDIUM by default; probe.high is HIGH → denied.
    with pytest.raises(PermissionDenied):
        registry.execute(_spec("probe.high"), source="llm")


def test_registry_default_source_is_safe_low_cap():
    bus, registry = _build()
    # No source supplied ⇒ defaults to "auto" (cap = LOW).
    # A HIGH-permission action must be denied.
    with pytest.raises(PermissionDenied):
        registry.execute(_spec("probe.high"))


# ------------------------------------------------------------------
# Schema validation is enforced at the registry
# ------------------------------------------------------------------
def test_registry_rejects_unknown_parameter_for_known_action():
    bus = EventBus()
    engine = ExecutionEngine(bus)
    registry = CommandRegistry(
        bus, engine,
        manifest=PluginManifest.permissive(),
        auto_confirm=True,
    )

    class _Owner:
        pass

    def _ok(path: str):
        return CommandResult(success=True, message="ok")

    engine.register("file.create", _ok, plugin_instance=_Owner())
    registry.register_metadata(
        "file.create", plugin="t", permission_level=PermissionLevel.MEDIUM
    )
    with pytest.raises(SchemaError):
        registry.execute(
            _spec("file.create", {"path": "x", "unexpected": 1}),
            source="cli",
        )


def test_registry_rejects_malformed_payload():
    _, registry = _build()
    with pytest.raises(SchemaError):
        registry.execute("not a dict", source="cli")


# ------------------------------------------------------------------
# Safety gate fires for destructive actions
# ------------------------------------------------------------------
def test_registry_fires_safety_gate_for_destructive_commands():
    bus, registry = _build(auto_confirm=False)

    # Stub gate that records the request instead of blocking on stdin.
    calls: list[dict] = []

    class _StubGate:
        def request(self, *, action, params, source, permission, trace_id):
            calls.append({"action": action, "source": source})

    registry.attach_security(safety_gate=_StubGate(), auto_confirm=False)
    registry.execute(_spec("probe.destructive"), source="cli")
    assert calls and calls[0]["action"] == "probe.destructive"
    assert calls[0]["source"] == "cli"


def test_registry_safety_gate_denial_propagates():
    bus, registry = _build(auto_confirm=False)

    class _DenyingGate:
        def request(self, **kw):
            raise ConfirmationDenied("nope")

    registry.attach_security(safety_gate=_DenyingGate(), auto_confirm=False)
    with pytest.raises(ConfirmationDenied):
        registry.execute(_spec("probe.destructive"), source="cli")


# ------------------------------------------------------------------
# Enforcement ordering: rate limit is cheaper than permission, so it
# must come first; but both must be rejected before dispatch.
# ------------------------------------------------------------------
def test_registry_blocks_before_dispatch_when_rate_limited():
    bus = EventBus()
    engine = ExecutionEngine(bus)
    registry = CommandRegistry(
        bus, engine,
        manifest=PluginManifest.permissive(),
        auto_confirm=True,
    )
    registry.attach_security(
        rate_limiter=RateLimiter(max_per_minute=1, repeat_threshold=1000)
    )
    called: list[bool] = []

    class _Owner:
        pass

    def _record():
        called.append(True)
        return CommandResult(True, "ok")

    engine.register("probe.rl", _record, plugin_instance=_Owner())
    registry.register_metadata(
        "probe.rl", plugin="t", permission_level=PermissionLevel.LOW
    )
    # First call consumes the quota and actually dispatches.
    registry.execute(_spec("probe.rl"), source="cli")
    assert called == [True]
    called.clear()
    # Second call is rate-limited and MUST NOT reach the handler.
    with pytest.raises(RateLimitError):
        registry.execute(_spec("probe.rl"), source="cli")
    assert called == []


# ------------------------------------------------------------------
# Source normalisation: empty/whitespace source is rejected.
# ------------------------------------------------------------------
@pytest.mark.parametrize("bad", ["", "   ", None])
def test_registry_rejects_invalid_source(bad):
    _, registry = _build()
    with pytest.raises(SchemaError):
        registry.execute(_spec("probe.low"), source=bad)  # type: ignore[arg-type]
