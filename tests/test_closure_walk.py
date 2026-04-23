"""
DESTRUCTION TEST: closure-walk bypass must be impossible.

Non-negotiable property
-----------------------
Walk every closure reachable from ``registry._executor.execute``.  Every
cell must be either:

1. NOT callable, OR
2. the registry's own safe pipeline function (the one that performs
   schema -> rate-limit -> permission -> safety-gate -> worker IPC).

If any other callable is reachable -> FAIL.

If a callable IS found (it will be - the safe pipeline is reachable by
design), calling it MUST still enforce the full security pipeline.
Specifically, calling a found callable with a HIGH-permission action
from an ``llm`` source MUST raise :class:`PermissionDenied`.
"""
from __future__ import annotations

import pytest

from aura.core.errors import PermissionDenied, RateLimitError
from aura.core.event_bus import EventBus
from aura.core.result import CommandResult
from aura.core.schema import CommandSpec
from aura.runtime.command_registry import (
    CommandRegistry,
    assert_safe_closures,
)
from aura.runtime.execution_engine import ExecutionEngine
from aura.security.permissions import PermissionLevel
from aura.security.plugin_manifest import PluginManifest
from aura.security.rate_limiter import RateLimiter
from tests._inprocess_port import InProcessWorkerPort


# ---------------------------------------------------------------------
# Fixture: a registry with a low- and a high-permission action wired up.
# ---------------------------------------------------------------------
def _build():
    bus = EventBus()
    engine = ExecutionEngine(bus)

    class _Owner:
        pass

    owner = _Owner()
    engine.register(
        "probe.low", lambda: CommandResult(True, "ok"),
        plugin_instance=owner,
    )
    engine.register(
        "probe.high", lambda: CommandResult(True, "ok"),
        plugin_instance=owner,
    )

    registry = CommandRegistry(
        bus, InProcessWorkerPort(engine),
        manifest=PluginManifest.permissive(),
        auto_confirm=True,
        rate_limiter=RateLimiter(max_per_minute=1, repeat_threshold=1000),
    )
    registry.register_metadata(
        "probe.low", plugin="t", permission_level=PermissionLevel.LOW
    )
    registry.register_metadata(
        "probe.high", plugin="t", permission_level=PermissionLevel.HIGH
    )
    return bus, registry


# ---------------------------------------------------------------------
# 1) The proxy's execute method captures exactly ONE cell; its contents
#    are a callable (the safe pipeline).
# ---------------------------------------------------------------------
def test_proxy_execute_captures_exactly_one_cell():
    _, registry = _build()
    proxy_execute = registry._executor.execute
    cells = proxy_execute.__func__.__closure__ or ()
    assert len(cells) == 1, (
        f"proxy.execute must capture exactly one cell (the safe "
        f"pipeline); got {len(cells)}: "
        f"{[type(c.cell_contents).__name__ for c in cells]}"
    )
    assert callable(cells[0].cell_contents)


# ---------------------------------------------------------------------
# 2) Walk the safe pipeline's own closure.  EVERY cell must be
#    non-callable.  If any callable appears here, that's a raw dispatch
#    bypass.
# ---------------------------------------------------------------------
def test_safe_pipeline_closure_contains_no_callables():
    _, registry = _build()
    proxy_execute = registry._executor.execute
    safe_pipeline = proxy_execute.__func__.__closure__[0].cell_contents

    cells = getattr(safe_pipeline, "__closure__", None) or ()
    offenders: list[tuple[str, type]] = []
    for cell in cells:
        try:
            obj = cell.cell_contents
        except ValueError:
            continue
        if callable(obj):
            offenders.append((repr(obj), type(obj)))

    assert not offenders, (
        "Unsafe callables found in _execute_safe.__closure__:\n  "
        + "\n  ".join(f"{r}  ({t.__name__})" for r, t in offenders)
    )


# ---------------------------------------------------------------------
# 3) The module-level audit walker must agree.
# ---------------------------------------------------------------------
def test_assert_safe_closures_accepts_fresh_registry():
    _, registry = _build()
    assert_safe_closures(registry)


# ---------------------------------------------------------------------
# 4) Even if an attacker reaches the ONE allowed callable via closure
#    walk, calling it still enforces the security pipeline.  HIGH-
#    permission actions from llm source MUST be denied.
# ---------------------------------------------------------------------
def test_callable_reached_via_closure_walk_still_enforces_permission():
    _, registry = _build()
    proxy_execute = registry._executor.execute
    callables = [
        c.cell_contents
        for c in (proxy_execute.__func__.__closure__ or ())
        if callable(c.cell_contents)
    ]
    assert callables, "proxy.execute must expose the safe pipeline via closure"
    safe_pipeline = callables[0]

    # EXPECTED: permission check enforced when calling the closure-
    # captured function with a HIGH action as llm.
    with pytest.raises(PermissionDenied):
        safe_pipeline(
            CommandSpec(action="probe.high", params={}, requires_confirm=False),
            "llm",
        )


# ---------------------------------------------------------------------
# 5) Rate limit is also enforced on the closure-captured callable.
# ---------------------------------------------------------------------
def test_callable_reached_via_closure_walk_still_enforces_rate_limit():
    _, registry = _build()
    proxy_execute = registry._executor.execute
    safe_pipeline = proxy_execute.__func__.__closure__[0].cell_contents

    # Burn the budget via the SUPPORTED API.
    registry.execute(
        CommandSpec(action="probe.low", params={}, requires_confirm=False),
        source="cli",
    )
    # Closure-captured callable still hits the rate-limit gate.
    with pytest.raises(RateLimitError):
        safe_pipeline(
            CommandSpec(action="probe.low", params={}, requires_confirm=False),
            "cli",
        )


# ---------------------------------------------------------------------
# 6) Recursive closure walk (transitive).  Ensure NO callable is
#    reachable anywhere in the graph except the safe pipeline.
# ---------------------------------------------------------------------
def test_transitive_closure_walk_finds_only_safe_pipeline():
    _, registry = _build()
    proxy_execute = registry._executor.execute
    cells = proxy_execute.__func__.__closure__ or ()
    assert len(cells) == 1
    safe_pipeline = cells[0].cell_contents

    visited: set[int] = set()
    offenders: list[str] = []

    def walk(fn, depth=0):
        if id(fn) in visited or depth > 8:
            return
        visited.add(id(fn))
        cells = getattr(fn, "__closure__", None) or ()
        for cell in cells:
            try:
                obj = cell.cell_contents
            except ValueError:
                continue
            if callable(obj):
                if obj is safe_pipeline:
                    continue
                offenders.append(
                    f"{repr(obj)[:120]} (type={type(obj).__name__})"
                )
                walk(obj, depth + 1)

    walk(safe_pipeline)
    assert not offenders, (
        "Transitive closure walk found unsafe callables:\n  "
        + "\n  ".join(offenders)
    )


# ---------------------------------------------------------------------
# 7) The proxy's non-execute methods also satisfy the invariant.
#    (__getattribute__, __setattr__, etc. may capture frozensets,
#    never callables.)
# ---------------------------------------------------------------------
def test_proxy_dunder_methods_have_no_unsafe_closures():
    _, registry = _build()
    proxy = registry._executor
    cls = type(proxy)
    for name in ("__getattribute__", "__setattr__", "__delattr__",
                 "__dir__", "__repr__"):
        fn = cls.__dict__.get(name)
        if fn is None:
            continue
        cells = getattr(fn, "__closure__", None) or ()
        for cell in cells:
            try:
                obj = cell.cell_contents
            except ValueError:
                continue
            assert not callable(obj), (
                f"{cls.__name__}.{name} closure contains unsafe "
                f"callable: {obj!r}"
            )


# ---------------------------------------------------------------------
# 8) The executor map lives ONLY inside the port (which wraps an
#    engine in tests; the production path has no engine at all).
#    The registry's closures must NOT capture the engine or any map
#    whose values are callables.
# ---------------------------------------------------------------------
def test_registry_closure_does_not_capture_executor_map():
    _, registry = _build()
    proxy_execute = registry._executor.execute
    safe_pipeline = proxy_execute.__func__.__closure__[0].cell_contents

    for cell in getattr(safe_pipeline, "__closure__", None) or ():
        try:
            obj = cell.cell_contents
        except ValueError:
            continue
        # Catch the old-style bug: a dict whose values are callables
        # means an executors map has landed in the closure.
        if isinstance(obj, dict):
            for v in obj.values():
                assert not callable(v), (
                    f"Closure captures a dict with callable values - "
                    f"looks like the executor map: {obj!r}"
                )
        # Catch: ExecutionEngine instance reached from the main-process
        # registry would be a regression.
        assert type(obj).__name__ != "ExecutionEngine", (
            "ExecutionEngine instance reached via registry closure - "
            "the engine must live only inside the worker process"
        )
