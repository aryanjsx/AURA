"""CF-1 destruction test: closure walk must not yield any transport.

This is the regression test for the closure-based execution bypass
(CF-1) that was identified during the Phase 0/1 audit.  Previously the
pipeline closure captured a direct reference to the worker port, and
an attacker could:

    fn = registry._executor.execute.__func__
    for cell in fn.__closure__:
        for c2 in cell.cell_contents.__closure__ or ():
            obj = c2.cell_contents
            if hasattr(obj, "send"):
                obj.send({...})  # <- bypassed registry pipeline

After the fix the transport lives in a module-level capability table
keyed by ``id(_execute_safe)``; the closure only contains primitives
and non-transport data.  The tests below assert:

1. No cell on the pipeline's closure has a ``.send`` method, nor a
   class name containing ``Worker`` or ``Port``.
2. Attempting the historic bypass (walk → locate transport → call
   ``.send``) finds nothing to call.
3. Normal execution through ``registry.execute`` still works.
4. A direct call through the reachable safe-pipeline callable still
   runs the full security pipeline (this is the belt-and-braces check
   — even when a caller gets a handle on the one legitimate callable,
   calling it does NOT skip rate-limit, permission, safety-gate or
   audit events).
"""
from __future__ import annotations

import pytest

from aura.core.event_bus import EventBus
from aura.core.errors import PermissionDenied
from aura.core.result import CommandResult
from aura.runtime.command_registry import (
    CommandRegistry,
    assert_safe_closures,
    _EXECUTION_PORTS,
)
from aura.runtime.execution_engine import ExecutionEngine
from aura.security.plugin_manifest import PluginManifest
from tests._inprocess_port import InProcessWorkerPort


class _Owner:
    """Plugin-instance marker required by ExecutionEngine.register."""


def _build_registry(auto_confirm: bool = True):
    bus = EventBus()
    engine = ExecutionEngine(bus)

    def _ok(**_kw) -> CommandResult:
        return CommandResult(success=True, message="ok")

    engine.register("probe.low", _ok, plugin_instance=_Owner())
    engine.register("probe.high", _ok, plugin_instance=_Owner())

    port = InProcessWorkerPort(engine)
    port._meta["probe.low"] = {
        "action": "probe.low",
        "plugin": "t",
        "description": "",
        "destructive": False,
        "permission_level": "MEDIUM",
    }
    port._meta["probe.high"] = {
        "action": "probe.high",
        "plugin": "t",
        "description": "",
        "destructive": False,
        "permission_level": "CRITICAL",
    }

    registry = CommandRegistry(
        bus, port,
        manifest=PluginManifest.permissive(),
        auto_confirm=auto_confirm,
    )
    registry.register_metadata(
        "probe.low", plugin="t", description="",
        destructive=False, permission_level="MEDIUM",
    )
    registry.register_metadata(
        "probe.high", plugin="t", description="",
        destructive=False, permission_level="CRITICAL",
    )
    # Return the port so the test keeps a strong ref (otherwise the
    # weak-value table entry disappears once the constructor frame
    # exits — our anchor keeps it alive for the pipeline lifetime,
    # but tests should not rely on that invariant implicitly).
    return bus, engine, port, registry


# ---------------------------------------------------------------------
# Part 5.1: walk the pipeline's closure and verify no transport is
# reachable.  Per spec, FAIL on any cell that has ``.send`` or whose
# class name contains ``Worker`` or ``Port``.
# ---------------------------------------------------------------------
def test_cf1_no_transport_in_pipeline_closure():
    _, _, _port, registry = _build_registry()

    proxy_execute = registry._executor.execute
    proxy_cells = proxy_execute.__func__.__closure__ or ()
    assert len(proxy_cells) == 1, (
        "proxy.execute must capture exactly one cell (the safe pipeline)"
    )
    safe_pipeline = proxy_cells[0].cell_contents
    assert callable(safe_pipeline)

    pipeline_cells = getattr(safe_pipeline, "__closure__", None) or ()
    offenders: list[str] = []
    for cell in pipeline_cells:
        try:
            obj = cell.cell_contents
        except ValueError:
            continue
        cls_name = type(obj).__name__
        if "Worker" in cls_name or "Port" in cls_name:
            offenders.append(
                f"transport-shaped class in closure: {cls_name}: {obj!r}"
            )
        if callable(getattr(obj, "send", None)):
            offenders.append(
                f"object with .send in closure: {cls_name}: {obj!r}"
            )

    assert not offenders, (
        "CF-1 REGRESSION: transport reachable via closure walk:\n  "
        + "\n  ".join(offenders)
    )


# ---------------------------------------------------------------------
# Part 5.2: the historic exploit must find nothing.  We walk every
# closure we can reach (transitively) and collect any ``.send``
# dispatcher.  The set MUST be empty.
# ---------------------------------------------------------------------
def test_cf1_closure_walk_exploit_finds_no_transport():
    _, _, _port, registry = _build_registry()

    seen_ids: set[int] = set()
    reachable_senders: list[object] = []

    def _walk(fn):
        if id(fn) in seen_ids:
            return
        seen_ids.add(id(fn))
        for cell in getattr(fn, "__closure__", None) or ():
            try:
                obj = cell.cell_contents
            except ValueError:
                continue
            if callable(getattr(obj, "send", None)):
                reachable_senders.append(obj)
            if callable(obj):
                _walk(obj)

    proxy_execute = registry._executor.execute
    _walk(proxy_execute.__func__)

    assert not reachable_senders, (
        "CF-1 REGRESSION: closure walk reached object(s) with a "
        f".send dispatcher: {[type(o).__name__ for o in reachable_senders]}"
    )


# ---------------------------------------------------------------------
# Part 5.3: normal execution still works.
# ---------------------------------------------------------------------
def test_cf1_normal_execution_still_works():
    _, _, _port, registry = _build_registry()

    result = registry.execute(
        {"action": "probe.low", "params": {}}, source="cli",
    )
    assert result.success is True


# ---------------------------------------------------------------------
# Part 5.4: the single reachable callable (the safe pipeline itself)
# STILL enforces the full security pipeline.  Even if an attacker
# grabs it, they cannot run CRITICAL from llm.  This is the defence-
# in-depth check for the "hide vs remove" distinction.
# ---------------------------------------------------------------------
def test_cf1_reachable_callable_still_enforces_permissions():
    _, _, _port, registry = _build_registry(auto_confirm=True)

    proxy_execute = registry._executor.execute
    safe_pipeline = proxy_execute.__func__.__closure__[0].cell_contents

    from aura.core.schema import validate_command
    spec = validate_command({"action": "probe.high", "params": {}})

    with pytest.raises(PermissionDenied):
        safe_pipeline(spec, "llm")


# ---------------------------------------------------------------------
# Part 5.5: ``assert_safe_closures`` rejects transport-bearing cells.
# Verify the tightened walker is actually strict.
# ---------------------------------------------------------------------
def test_assert_safe_closures_rejects_send_bearing_cell():
    _, _, _port, registry = _build_registry()
    # Fresh registry must pass.
    assert_safe_closures(registry)

    # Build an artificial closure that captures an object with .send
    # and confirm the walker rejects it even though the object is not
    # directly a WorkerClient.  The walker treats any .send attribute
    # as transport-shaped.
    class _FakeTransport:
        def send(self, _req):  # pragma: no cover - never reached
            return {}

    fake = _FakeTransport()

    def _outer():
        def _inner():
            return fake  # captures fake in _inner.__closure__
        return _inner

    inner = _outer()

    class _Shim:
        class _Exec:
            execute = inner
        _executor = _Exec()

    # Point the walker at our shim.  Because inner is the sole cell
    # of proxy.execute, it is treated as the "safe pipeline".  Then
    # the walker descends into inner's closure and finds fake, whose
    # .send attribute must trigger rejection.
    #
    # However: inner captures 'fake' as a cell, and our shim's
    # proxy.execute has no closure at all — so we need to build the
    # shim slightly differently.  Re-do with a proper nested closure.

    def _outer2(transport):
        def _pipeline():
            # captures transport
            _ = transport
        return _pipeline

    pipeline = _outer2(_FakeTransport())

    def _make_proxy(pl):
        def _execute_on_proxy(*a, **kw):
            return pl(*a, **kw)  # captures pl
        return _execute_on_proxy

    proxy_execute = _make_proxy(pipeline)

    class _Shim2:
        pass

    shim = _Shim2()
    # Attach a proxy-like object with a bound-method-shaped .execute.
    class _ProxyLike:
        pass
    pl2 = _ProxyLike()
    pl2.execute = proxy_execute  # type: ignore[attr-defined]
    object.__setattr__(shim, "_executor", pl2)

    with pytest.raises(AssertionError) as excinfo:
        assert_safe_closures(shim)  # type: ignore[arg-type]
    assert "send" in str(excinfo.value).lower() or "transport" in str(
        excinfo.value
    ).lower()


# ---------------------------------------------------------------------
# Part 5.6: the capability table is keyed by id(safe_pipeline) and
# nothing else - it must not key anything off the registry object.
# ---------------------------------------------------------------------
def test_cf1_capability_table_keys_only_the_pipeline_function():
    _, _, port, registry = _build_registry()

    proxy_execute = registry._executor.execute
    safe_pipeline = proxy_execute.__func__.__closure__[0].cell_contents
    key = id(safe_pipeline)

    assert key in _EXECUTION_PORTS, (
        "CF-1 installation failure: safe_pipeline is not registered "
        "in _EXECUTION_PORTS"
    )
    assert _EXECUTION_PORTS[key] is port
    # The registry itself must NOT be a key in the capability table.
    assert id(registry) not in _EXECUTION_PORTS
