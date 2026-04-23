"""CommandRegistry + ExecutionEngine tests."""
from __future__ import annotations

import pytest

from aura.runtime.command_registry import CommandRegistry
from aura.core.errors import EngineError, RegistryError, SchemaError
from aura.core.event_bus import EventBus
from aura.runtime.execution_engine import ExecutionEngine
from aura.security.permissions import PermissionLevel
from aura.security.plugin_manifest import PluginManifest
from aura.core.result import CommandResult
from aura.core.schema import CommandSpec
from tests._inprocess_port import InProcessWorkerPort


def _echo(**kwargs) -> CommandResult:
    return CommandResult(success=True, message="ok", data=kwargs)


def _build() -> tuple[CommandRegistry, ExecutionEngine, EventBus, object]:
    bus = EventBus()
    engine = ExecutionEngine(bus)
    registry = CommandRegistry(
        bus, InProcessWorkerPort(engine), manifest=PluginManifest.permissive()
    )

    class _Owner:  # sentinel plugin instance
        pass

    owner = _Owner()
    return registry, engine, bus, owner


def test_duplicate_executor_registration_blocked():
    registry, engine, _, owner = _build()
    engine.register("echo", _echo, plugin_instance=owner)
    with pytest.raises(EngineError):
        engine.register("echo", _echo, plugin_instance=owner)


def test_duplicate_metadata_registration_blocked():
    registry, engine, _, owner = _build()
    engine.register("echo", _echo, plugin_instance=owner)
    registry.register_metadata("echo", plugin="t", permission_level=PermissionLevel.LOW)
    with pytest.raises(RegistryError):
        registry.register_metadata("echo", plugin="t")


def test_unknown_action_raises():
    registry, _, _, _ = _build()
    with pytest.raises(RegistryError):
        registry.execute({"action": "nope", "params": {}, "requires_confirm": False})


def test_malformed_payload_raises_schema_error():
    registry, _, _, _ = _build()
    with pytest.raises(SchemaError):
        registry.execute("not a dict")
    with pytest.raises(SchemaError):
        registry.execute({"params": {}})
    with pytest.raises(SchemaError):
        registry.execute({"action": "x", "params": "bad"})


def test_happy_path_dispatches_through_engine():
    registry, engine, _, owner = _build()
    engine.register("echo", _echo, plugin_instance=owner)
    registry.register_metadata(
        "echo", plugin="t", permission_level=PermissionLevel.LOW,
    )
    result = registry.execute(
        CommandSpec(action="echo", params={"a": 1}, requires_confirm=False)
    )
    assert result.success is True
    assert result.data == {"a": 1}
    assert result.command_type == "echo"


def test_registry_holds_no_handler_reference():
    registry, engine, _, owner = _build()
    engine.register("echo", _echo, plugin_instance=owner)
    registry.register_metadata(
        "echo", plugin="t", permission_level=PermissionLevel.LOW,
    )
    entry = registry.get("echo")
    assert not hasattr(entry, "handler")


def test_engine_hides_executor_dict():
    registry, engine, _, owner = _build()
    engine.register("echo", _echo, plugin_instance=owner)
    # The engine instance is held only by bootstrap code and never
    # leaks to the registry, so the exact attribute name no longer
    # matters for the security model — but the public/short-form
    # alias must still be absent.
    assert not hasattr(engine, "executors")
    assert engine.has("echo") is True
    assert engine._size() == 1
