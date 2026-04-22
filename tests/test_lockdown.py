"""
Phase-2 LOCKDOWN tests.

Each test corresponds to one bypass the previous red-team audit found.
If ANY of these fails, the lockdown has regressed and the system is
back in the "not safe" state.

Covers:
1. ``ExecutionEngine.dispatch`` does NOT exist as a public attribute.
2. ``CommandRegistry._engine`` does NOT exist as a public attribute.
3. ``WorkerClient.dispatch`` does NOT exist as a public attribute.
4. ``_seal()`` is one-shot; a second call refuses.
5. ``Intent`` construction with a ``source`` keyword raises TypeError
   (privilege escalation blocked).
6. ``CommandRegistry.register_metadata`` MUST refuse when no manifest
   is attached (fake-action registration blocked).
7. Manifest enforcement rejects unknown actions / flag mismatches via
   the registry's own check (defense in depth, not only the loader).
8. Action name length is capped at 256 characters.
9. Every successful execution emits the ``command.executing`` +
   ``command.completed`` audit events.
10. Router.execute_intent requires an explicit ``source`` keyword.
"""
from __future__ import annotations

import pytest

from aura.core.command_registry import CommandRegistry
from aura.core.errors import RegistryError, SchemaError
from aura.core.event_bus import EventBus
from aura.core.execution_engine import ExecutionEngine
from aura.core.intent import Intent
from aura.core.permissions import PermissionLevel
from aura.core.plugin_manifest import (
    ManifestEntry,
    PluginManifest,
    PluginManifestError,
)
from aura.core.result import CommandResult
from aura.core.router import Router
from aura.core.schema import CommandSpec
from aura.core.worker_client import WorkerClient


# ---------------------------------------------------------------------------
# 1) Engine has NO public dispatch
# ---------------------------------------------------------------------------
def test_engine_has_no_public_dispatch():
    engine = ExecutionEngine(EventBus())
    assert not hasattr(engine, "dispatch"), (
        "ExecutionEngine.dispatch must be private (name-mangled)"
    )


def test_engine_private_dispatch_is_name_mangled_only():
    """The mangled name exists (because the method body lives on the
    class), but no callable dispatch attribute is exposed under a
    public or single-underscore name."""
    engine = ExecutionEngine(EventBus())
    # Name-mangled lookup works only via the explicit mangled name.
    mangled = getattr(engine, "_ExecutionEngine__dispatch", None)
    assert callable(mangled)
    # But the short forms are gone.
    assert getattr(engine, "dispatch", None) is None
    assert getattr(engine, "_dispatch", None) is None


# ---------------------------------------------------------------------------
# 2) CommandRegistry stores no engine reference under a discoverable name
# ---------------------------------------------------------------------------
def test_registry_does_not_expose_engine_attribute():
    bus = EventBus()
    engine = ExecutionEngine(bus)
    registry = CommandRegistry(bus, engine, manifest=PluginManifest.permissive())
    assert not hasattr(registry, "_engine"), (
        "CommandRegistry must not expose the engine on any single-underscore "
        "attribute"
    )
    assert not hasattr(registry, "engine"), (
        "CommandRegistry must not expose the engine publicly"
    )
    # The dispatch capability is stashed under a name-mangled slot; the
    # engine object itself is NOT stored anywhere on the registry.
    mangled = getattr(registry, "_CommandRegistry__dispatch", None)
    assert callable(mangled)


# ---------------------------------------------------------------------------
# 3) WorkerClient has NO public dispatch
# ---------------------------------------------------------------------------
def test_worker_client_has_no_public_dispatch():
    # We do NOT start the worker; attribute-surface inspection only.
    client = WorkerClient(EventBus())
    assert not hasattr(client, "dispatch"), (
        "WorkerClient.dispatch must be private (name-mangled)"
    )
    assert not hasattr(client, "_dispatch")
    # Mangled form exists because the method lives on the class.
    mangled = getattr(client, "_WorkerClient__dispatch", None)
    assert callable(mangled)


# ---------------------------------------------------------------------------
# 4) _seal() is one-shot
# ---------------------------------------------------------------------------
def test_engine_seal_is_one_shot():
    engine = ExecutionEngine(EventBus())
    first = engine._seal()
    assert callable(first)
    with pytest.raises(RuntimeError):
        engine._seal()
    assert engine.sealed is True


def test_worker_client_seal_is_one_shot():
    client = WorkerClient(EventBus())
    first = client._seal()
    assert callable(first)
    with pytest.raises(RuntimeError):
        client._seal()
    assert client.sealed is True


# ---------------------------------------------------------------------------
# 5) Intent rejects caller-provided source
# ---------------------------------------------------------------------------
def test_intent_construction_rejects_source_kwarg():
    with pytest.raises(TypeError):
        Intent(action="file.delete", source="cli")  # type: ignore[call-arg]


def test_intent_has_no_source_attribute():
    intent = Intent(action="system.cpu")
    assert not hasattr(intent, "source")


# ---------------------------------------------------------------------------
# 6) register_metadata without a manifest is refused
# ---------------------------------------------------------------------------
def test_registry_refuses_registration_without_manifest():
    bus = EventBus()
    engine = ExecutionEngine(bus)
    registry = CommandRegistry(bus, engine, manifest=None)
    with pytest.raises(RegistryError) as excinfo:
        registry.register_metadata(
            "fake.action", plugin="x", permission_level=PermissionLevel.LOW
        )
    assert "manifest" in str(excinfo.value).lower()


# ---------------------------------------------------------------------------
# 7) Manifest enforces unknown-action and flag-mismatch in the REGISTRY
#    (not only inside the plugin loader)
# ---------------------------------------------------------------------------
def test_registry_rejects_unknown_action_against_manifest():
    bus = EventBus()
    engine = ExecutionEngine(bus)
    manifest = PluginManifest(
        {
            "known.action": ManifestEntry(
                plugin="x",
                action="known.action",
                permission_level=PermissionLevel.LOW,
                destructive=False,
                audit_events=("command.executing",),
            ),
        }
    )
    registry = CommandRegistry(bus, engine, manifest=manifest)

    with pytest.raises(RegistryError) as excinfo:
        registry.register_metadata(
            "unknown.action",
            plugin="x",
            permission_level=PermissionLevel.LOW,
        )
    assert "unknown" in str(excinfo.value).lower()


def test_registry_rejects_destructive_flag_lie():
    bus = EventBus()
    engine = ExecutionEngine(bus)
    manifest = PluginManifest(
        {
            "x.rm": ManifestEntry(
                plugin="x",
                action="x.rm",
                permission_level=PermissionLevel.HIGH,
                destructive=True,
                audit_events=("command.destructive",),
            ),
        }
    )
    registry = CommandRegistry(bus, engine, manifest=manifest)
    with pytest.raises(RegistryError) as excinfo:
        registry.register_metadata(
            "x.rm",
            plugin="x",
            permission_level=PermissionLevel.HIGH,
            destructive=False,  # plugin LIES that it's safe
        )
    assert "destructive" in str(excinfo.value).lower()


def test_registry_rejects_permission_lie():
    bus = EventBus()
    engine = ExecutionEngine(bus)
    manifest = PluginManifest(
        {
            "x.a": ManifestEntry(
                plugin="x",
                action="x.a",
                permission_level=PermissionLevel.HIGH,
                destructive=False,
                audit_events=("command.executing",),
            ),
        }
    )
    registry = CommandRegistry(bus, engine, manifest=manifest)
    with pytest.raises(RegistryError) as excinfo:
        registry.register_metadata(
            "x.a",
            plugin="x",
            permission_level=PermissionLevel.LOW,  # LIES
            destructive=False,
        )
    assert "permission_level" in str(excinfo.value)


# ---------------------------------------------------------------------------
# 8) Action name length cap
# ---------------------------------------------------------------------------
def test_validate_command_rejects_oversized_action_name():
    from aura.core.schema import MAX_ACTION_NAME_LEN, validate_command

    oversized = "x" * (MAX_ACTION_NAME_LEN + 1)
    with pytest.raises(SchemaError) as excinfo:
        validate_command({"action": oversized, "params": {}})
    assert str(MAX_ACTION_NAME_LEN) in str(excinfo.value)


def test_validate_command_accepts_name_exactly_at_limit():
    from aura.core.schema import MAX_ACTION_NAME_LEN, validate_command

    at_limit = "x" * MAX_ACTION_NAME_LEN
    # No raise.
    spec = validate_command({"action": at_limit, "params": {}})
    assert spec.action == at_limit


# ---------------------------------------------------------------------------
# 9) Every successful execution emits the audit lifecycle pair
# ---------------------------------------------------------------------------
def test_registry_emits_audit_events_on_every_execution():
    bus = EventBus()
    engine = ExecutionEngine(bus)
    registry = CommandRegistry(
        bus, engine, manifest=PluginManifest.permissive(), auto_confirm=True,
    )

    class _Owner:
        pass

    engine.register(
        "audit.probe", lambda: CommandResult(True, "ok"),
        plugin_instance=_Owner(),
    )
    registry.register_metadata(
        "audit.probe", plugin="t", permission_level=PermissionLevel.LOW,
    )

    events: list[str] = []
    bus.subscribe("command.executing", lambda env: events.append(env["event"]))
    bus.subscribe("command.completed", lambda env: events.append(env["event"]))

    registry.execute(
        CommandSpec(action="audit.probe", params={}, requires_confirm=False),
        source="cli",
    )
    assert "command.executing" in events
    assert "command.completed" in events


def test_destructive_execution_emits_destructive_event():
    bus = EventBus()
    engine = ExecutionEngine(bus)
    manifest = PluginManifest(
        {
            "audit.destructive": ManifestEntry(
                plugin="t",
                action="audit.destructive",
                permission_level=PermissionLevel.HIGH,
                destructive=True,
                audit_events=("command.destructive",),
            ),
        }
    )
    registry = CommandRegistry(
        bus, engine, manifest=manifest, auto_confirm=True,
    )

    class _Owner:
        pass

    engine.register(
        "audit.destructive", lambda: CommandResult(True, "wiped"),
        plugin_instance=_Owner(),
    )
    registry.register_metadata(
        "audit.destructive",
        plugin="t",
        permission_level=PermissionLevel.HIGH,
        destructive=True,
    )

    destructive: list[str] = []
    bus.subscribe(
        "command.destructive",
        lambda env: destructive.append(env["payload"].get("action")),
    )
    registry.execute(
        CommandSpec(action="audit.destructive", params={},
                    requires_confirm=False),
        source="cli",
    )
    assert destructive == ["audit.destructive"]


# ---------------------------------------------------------------------------
# 10) Router.execute_intent requires explicit ``source``
# ---------------------------------------------------------------------------
def test_router_execute_intent_requires_source():
    bus = EventBus()
    engine = ExecutionEngine(bus)
    registry = CommandRegistry(bus, engine, manifest=PluginManifest.permissive())

    class _Owner:
        pass

    engine.register(
        "r.probe", lambda: CommandResult(True, "ok"),
        plugin_instance=_Owner(),
    )
    registry.register_metadata(
        "r.probe", plugin="t", permission_level=PermissionLevel.LOW,
    )
    router = Router(bus, registry, intent_parsers=[])

    intent = Intent(action="r.probe", args={})
    # Missing source → TypeError (required kwarg).
    with pytest.raises(TypeError):
        router.execute_intent(intent)  # type: ignore[call-arg]

    # Empty source → SchemaError (developer bug, fail loud).
    with pytest.raises(SchemaError):
        router.execute_intent(intent, source="   ")

    # With valid source → success (AutoConfirmGate by default).
    registry.attach_security(auto_confirm=True)
    result = router.execute_intent(intent, source="cli")
    assert result.success is True


# ---------------------------------------------------------------------------
# 11) Single entry point: calling the name-mangled dispatch by reflection
# still goes through no-security — proving the lockdown depends on the
# engine being unreachable from external references.  We DOCUMENT that a
# determined attacker with arbitrary reflection can still reach the
# mangled name; the lockdown's job is to remove every SUPPORTED path.
# ---------------------------------------------------------------------------
def test_reflection_reaches_mangled_but_no_supported_api_does():
    """Sanity: confirm the only reachable path to dispatch is the
    explicit mangled attribute — not any public method, not any
    single-underscore attribute.
    """
    engine = ExecutionEngine(EventBus())
    public_candidates = [
        "dispatch", "_dispatch", "execute", "_execute", "run", "_run",
        "invoke", "_invoke", "call", "_call",
    ]
    for name in public_candidates:
        assert not hasattr(engine, name), (
            f"Engine must not expose {name!r}; only the mangled "
            f"_ExecutionEngine__dispatch is reachable."
        )


# ---------------------------------------------------------------------------
# 12) bootstrap returns (router, registry) only — worker is NOT exposed
# ---------------------------------------------------------------------------
def test_bootstrap_signature_does_not_return_worker():
    import inspect

    from main import bootstrap

    sig = inspect.signature(bootstrap)
    # Return annotation should mention Router + CommandRegistry only —
    # we validate via a string check because runtime return typing is a
    # generic alias.
    anno = str(sig.return_annotation)
    assert "WorkerClient" not in anno, (
        f"bootstrap() must not return the WorkerClient; got {anno!r}"
    )
    assert "Router" in anno
    assert "CommandRegistry" in anno
