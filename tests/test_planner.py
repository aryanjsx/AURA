"""TaskPlanner tests — validation, execution, and rollback."""
from __future__ import annotations

import pytest

from aura.runtime.command_registry import CommandRegistry
from aura.core.errors import PlanError
from aura.core.event_bus import EventBus
from aura.runtime.execution_engine import ExecutionEngine
from aura.security.permissions import PermissionLevel
from aura.runtime.planner import TaskExecutor, TaskPlan, TaskStep
from aura.security.plugin_manifest import PluginManifest
from aura.security.rate_limiter import RateLimiter
from aura.core.result import CommandResult
from aura.runtime.router import Router
from aura.security.safety_gate import AutoConfirmGate


def _build_router(handlers: dict[str, tuple]) -> Router:
    bus = EventBus()
    engine = ExecutionEngine(bus)
    registry = CommandRegistry(bus, engine, manifest=PluginManifest.permissive())

    class _Owner:
        pass
    owner = _Owner()

    for action, (handler, level) in handlers.items():
        engine.register(action, handler, plugin_instance=owner)
        registry.register_metadata(
            action, plugin="test", permission_level=level,
        )

    return Router(
        bus,
        registry,
        intent_parsers=[],
        safety_gate=AutoConfirmGate(bus),
        rate_limiter=RateLimiter(max_per_minute=1000, repeat_threshold=1000),
        auto_confirm=True,
    )


def _ok(**kwargs) -> CommandResult:
    return CommandResult(success=True, message="ok", data=kwargs)


def _bad(**kwargs) -> CommandResult:
    return CommandResult(success=False, message="boom", data=kwargs)


def test_plan_validates_unknown_action():
    router = _build_router({"a": (_ok, PermissionLevel.LOW)})
    executor = TaskExecutor(router._bus, router)
    plan = TaskPlan(description="bad", steps=[
        TaskStep(action="does.not.exist"),
    ])
    with pytest.raises(PlanError):
        executor.validate(plan)


def test_plan_runs_all_steps():
    router = _build_router({
        "step.a": (_ok, PermissionLevel.LOW),
        "step.b": (_ok, PermissionLevel.LOW),
    })
    executor = TaskExecutor(router._bus, router)
    plan = TaskPlan(description="two-step", steps=[
        TaskStep(action="step.a", params={"x": 1}),
        TaskStep(action="step.b", params={"y": 2}),
    ])
    report = executor.execute(plan)
    assert report.success is True
    assert report.completed == ["step.a", "step.b"]


def test_plan_rolls_back_on_failure():
    rollbacks: list[str] = []

    def ok_a(**_kw) -> CommandResult:
        return CommandResult(success=True, message="a")

    def bad_b(**_kw) -> CommandResult:
        return CommandResult(success=False, message="b failed")

    def undo_a(**_kw) -> CommandResult:
        rollbacks.append("a")
        return CommandResult(success=True, message="undo a")

    router = _build_router({
        "step.a": (ok_a, PermissionLevel.LOW),
        "step.b": (bad_b, PermissionLevel.LOW),
        "undo.a": (undo_a, PermissionLevel.LOW),
    })
    executor = TaskExecutor(router._bus, router)
    plan = TaskPlan(description="rollback test", steps=[
        TaskStep(action="step.a", rollback_action="undo.a"),
        TaskStep(action="step.b"),
    ])
    report = executor.execute(plan)
    assert report.success is False
    assert report.failed_at == "step.b"
    assert report.completed == ["step.a"]
    assert rollbacks == ["a"]
    assert "undo.a" in report.rollbacks


def test_plan_with_too_many_steps_rejected():
    router = _build_router({"x": (_ok, PermissionLevel.LOW)})
    executor = TaskExecutor(router._bus, router)
    plan = TaskPlan(description="huge", steps=[
        TaskStep(action="x") for _ in range(100)
    ])
    with pytest.raises(PlanError):
        executor.validate(plan)
