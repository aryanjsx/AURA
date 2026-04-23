"""
Capability-lockdown self-tests (Phase-3, closure-walk-safe).

This suite pins every reflection-, mutation-, and capability-leak
vector the audits identified.  Unlike the previous Phase-2 tests
(which tested the now-removed capability-token handoff), this suite
asserts the stronger Phase-3 property: the registry's object graph
contains **no** reachable callable other than its own safe pipeline.
"""
from __future__ import annotations

import pytest

from aura.runtime.command_registry import (
    CommandRegistry,
    _make_executor_proxy,
    assert_safe_closures,
)
from aura.core.errors import (
    PermissionDenied,
    RateLimitError,
)
from aura.core.event_bus import EventBus
from aura.runtime.execution_engine import ExecutionEngine
from aura.security.permissions import PermissionLevel, PermissionValidator
from aura.security.plugin_manifest import PluginManifest
from aura.security.rate_limiter import RateLimiter
from aura.core.result import CommandResult
from aura.core.schema import CommandSpec
from aura.runtime.worker_client import WorkerClient
from tests._inprocess_port import InProcessWorkerPort


# ---------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------
def _registry(*, auto_confirm: bool = True, **kw):
    bus = EventBus()
    engine = ExecutionEngine(bus)

    class _Owner:
        pass

    engine.register(
        "probe.low", lambda: CommandResult(True, "ok"),
        plugin_instance=_Owner(),
    )
    engine.register(
        "probe.high", lambda: CommandResult(True, "ok"),
        plugin_instance=_Owner(),
    )

    registry = CommandRegistry(
        bus, InProcessWorkerPort(engine),
        manifest=PluginManifest.permissive(),
        auto_confirm=auto_confirm,
        **kw,
    )
    registry.register_metadata(
        "probe.low", plugin="t", permission_level=PermissionLevel.LOW
    )
    registry.register_metadata(
        "probe.high", plugin="t", permission_level=PermissionLevel.HIGH
    )
    return bus, engine, registry


# =====================================================================
# 1) BYPASS TESTS - known attack surface is gone
# =====================================================================
class TestBypassReflection:
    """Every named reflection vector identified in the audits."""

    @pytest.mark.parametrize(
        "name",
        [
            "_engine",
            "_worker",
            "_worker_port",
            "_dispatcher",
            "_dispatcher_source",
            "_dispatch",
            "__dispatch",
            "_seal",
            "_acquire_capability",
            "_CommandRegistry__dispatch",
            "_CommandRegistry__has",
            "_CommandRegistry__engine",
            "_CommandRegistry__worker",
            "attach_security",
            "attach_manifest",
            "engine",
            "worker",
            "dispatch",
        ],
    )
    def test_registry_attribute_is_unreachable(self, name):
        _, _, registry = _registry()
        assert not hasattr(registry, name), (
            f"Registry exposes {name!r} - bypass surface the lockdown "
            "was supposed to remove."
        )
        with pytest.raises(AttributeError):
            getattr(registry, name)

    def test_registry_dir_lists_only_public_api(self):
        _, _, registry = _registry()
        assert sorted(dir(registry)) == sorted(
            ["execute", "register_metadata", "unregister",
             "has", "get", "list"]
        )

    def test_registry_has_no_dict(self):
        _, _, registry = _registry()
        with pytest.raises(AttributeError):
            registry.__dict__  # noqa: B018

    def test_registry_vars_fails(self):
        _, _, registry = _registry()
        with pytest.raises(TypeError):
            vars(registry)

    @pytest.mark.parametrize(
        "name",
        ["dispatch", "_dispatch", "__dispatch",
         "_ExecutionEngine__dispatch", "_seal", "execute",
         "_acquire_capability"],
    )
    def test_engine_attribute_is_unreachable(self, name):
        engine = ExecutionEngine(EventBus())
        # ExecutionEngine.dispatch DOES exist now (worker-side only) -
        # but only inside the trusted worker.  Its existence here is
        # fine; what matters is it is NEVER reachable from the main-
        # process registry's object graph.
        if name == "dispatch":
            assert hasattr(engine, name)  # allowed on engine itself
            return
        assert not hasattr(engine, name), (
            f"ExecutionEngine still exposes {name!r}"
        )

    @pytest.mark.parametrize(
        "name",
        ["dispatch", "_dispatch", "__dispatch",
         "_WorkerClient__dispatch", "_seal", "execute",
         "_acquire_capability"],
    )
    def test_worker_attribute_is_unreachable(self, name):
        client = WorkerClient(EventBus())
        assert not hasattr(client, name), (
            f"WorkerClient still exposes {name!r}"
        )


class TestClosureWalkInvariant:
    """The core Phase-3 property: closure walks only reveal the safe
    pipeline, never a raw dispatcher."""

    def test_executor_proxy_exposes_only_execute(self):
        proxy = _make_executor_proxy(lambda spec, src: CommandResult(True, "x"))
        assert dir(proxy) == ["execute"]
        for name in ("_call", "_fn", "fn", "execute_raw", "__dict__"):
            with pytest.raises(AttributeError):
                getattr(proxy, name)

    def test_executor_proxy_is_immutable(self):
        proxy = _make_executor_proxy(lambda spec, src: CommandResult(True, "x"))
        with pytest.raises(AttributeError):
            proxy._call = lambda *a, **k: None  # type: ignore[misc]
        with pytest.raises(AttributeError):
            del proxy.execute  # type: ignore[misc]

    def test_assert_safe_closures_passes(self):
        _, _, registry = _registry()
        # Must not raise: every cell is non-callable or the safe pipeline.
        assert_safe_closures(registry)

    def test_closure_walk_reveals_only_safe_pipeline(self):
        """Explicit assertion the audit uses: walk the proxy's
        execute closure; the single callable found MUST be the safe
        pipeline function, and calling it MUST still enforce the
        security pipeline."""
        bus, engine, registry = _registry(
            rate_limiter=RateLimiter(max_per_minute=1, repeat_threshold=1000),
        )
        proxy_execute = registry._executor.execute
        cells = proxy_execute.__func__.__closure__ or ()
        callables = [c.cell_contents for c in cells if callable(c.cell_contents)]
        assert len(callables) == 1, (
            "proxy.execute must capture exactly one callable (the safe "
            f"pipeline); got {len(callables)}"
        )
        safe_pipeline = callables[0]

        # Now walk the pipeline's own closure: every cell must be NON-
        # callable.  If any callable appears here, it's a raw dispatch
        # bypass and the test fails.
        inner_cells = getattr(safe_pipeline, "__closure__", None) or ()
        for cell in inner_cells:
            try:
                obj = cell.cell_contents
            except ValueError:
                continue
            assert not callable(obj), (
                f"Unsafe callable found in _execute_safe.__closure__: "
                f"{obj!r} (type={type(obj).__name__}).  Only non-callable "
                "data is allowed in the safe pipeline's closure."
            )

        # Burn the rate-limit budget through the supported API.
        registry.execute(
            CommandSpec(action="probe.low", params={}, requires_confirm=False),
            source="cli",
        )
        # Calling the closure-captured function still hits the rate
        # limiter - proving it IS the safe pipeline, not a bypass.
        with pytest.raises(RateLimitError):
            safe_pipeline(
                CommandSpec(action="probe.low", params={}, requires_confirm=False),
                "cli",
            )


# =====================================================================
# 2) EXECUTION TEST - the only allowed path is registry.execute
# =====================================================================
class TestSingleExecutionPath:
    def test_supported_path_works(self):
        _, _, registry = _registry()
        result = registry.execute(
            CommandSpec(action="probe.low", params={}, requires_confirm=False),
            source="cli",
        )
        assert result.success is True

    def test_supported_path_enforces_permissions(self):
        _, _, registry = _registry()
        with pytest.raises(PermissionDenied):
            registry.execute(
                CommandSpec(
                    action="probe.high", params={}, requires_confirm=False
                ),
                source="llm",
            )

    def test_no_alternative_dispatch_method_exists(self):
        _, _, registry = _registry()
        for cand in ("dispatch", "_dispatch", "run", "_run",
                     "invoke", "_invoke", "call", "_call",
                     "execute_raw", "raw_execute"):
            assert not hasattr(registry, cand), (
                f"Registry must not provide alternative dispatch path "
                f"{cand!r}"
            )


# =====================================================================
# 3) WORKER ISOLATION - WorkerClient transport only
# =====================================================================
class TestWorkerIsolation:
    def test_worker_client_has_no_dispatch_methods(self):
        client = WorkerClient(EventBus())
        for name in (
            "dispatch", "execute", "run", "invoke", "call",
            "_dispatch", "__dispatch",
            "_WorkerClient__dispatch", "_seal",
            "_acquire_capability",
        ):
            assert not hasattr(client, name), (
                f"WorkerClient must not expose {name!r}"
            )

    def test_worker_client_is_not_callable(self):
        """Critical closure-walk requirement: the port MUST NOT be
        callable, otherwise it would appear as an unsafe cell in the
        registry's closure."""
        client = WorkerClient(EventBus())
        assert not callable(client)

    def test_inprocess_port_is_not_callable(self):
        engine = ExecutionEngine(EventBus())
        port = InProcessWorkerPort(engine)
        assert not callable(port)


# =====================================================================
# 4) MUTATION - every post-construction mutation is rejected
# =====================================================================
class TestImmutableRegistry:
    def test_cannot_replace_safety_gate(self):
        _, _, registry = _registry()
        with pytest.raises(AttributeError):
            registry._safety_gate = None  # type: ignore[misc]

    def test_cannot_replace_rate_limiter(self):
        _, _, registry = _registry()
        with pytest.raises(AttributeError):
            registry._rate_limiter = RateLimiter()  # type: ignore[misc]

    def test_cannot_replace_permissions(self):
        _, _, registry = _registry()
        with pytest.raises(AttributeError):
            registry._permissions = PermissionValidator()  # type: ignore[misc]

    def test_cannot_install_dispatch_shim(self):
        _, _, registry = _registry()
        with pytest.raises(AttributeError):
            registry._executor = lambda *a, **k: None  # type: ignore[misc]

    def test_cannot_install_attach_security(self):
        _, _, registry = _registry()
        with pytest.raises(AttributeError):
            registry.attach_security = lambda **kw: None  # type: ignore[misc]

    def test_cannot_delete_internals(self):
        _, _, registry = _registry()
        with pytest.raises(AttributeError):
            del registry._executor
        with pytest.raises(AttributeError):
            del registry._safety_gate

    def test_cannot_set_brand_new_attribute(self):
        _, _, registry = _registry()
        with pytest.raises(AttributeError):
            registry.totally_new = "x"  # type: ignore[attr-defined]

    def test_register_metadata_still_works_after_construction(self):
        bus = EventBus()
        engine = ExecutionEngine(bus)

        class _Owner:
            pass

        engine.register(
            "late.probe", lambda: CommandResult(True, "ok"),
            plugin_instance=_Owner(),
        )
        registry = CommandRegistry(
            bus, InProcessWorkerPort(engine),
            manifest=PluginManifest.permissive(),
            auto_confirm=True,
        )
        registry.register_metadata(
            "late.probe", plugin="t",
            permission_level=PermissionLevel.LOW,
        )
        result = registry.execute(
            CommandSpec(action="late.probe", params={}, requires_confirm=False),
            source="cli",
        )
        assert result.success is True
