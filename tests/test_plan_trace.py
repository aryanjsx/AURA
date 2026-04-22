"""TaskExecutor must give every step in a plan the SAME trace_id."""
from __future__ import annotations

from aura.core.command_registry import CommandRegistry
from aura.core.event_bus import EventBus
from aura.core.execution_engine import ExecutionEngine
from aura.core.permissions import PermissionLevel
from aura.core.planner import TaskExecutor, TaskPlan, TaskStep
from aura.core.plugin_manifest import PluginManifest
from aura.core.rate_limiter import RateLimiter
from aura.core.result import CommandResult
from aura.core.router import Router
from aura.core.safety_gate import AutoConfirmGate


def _build_router():
    bus = EventBus()
    engine = ExecutionEngine(bus)
    registry = CommandRegistry(bus, engine, manifest=PluginManifest.permissive())

    class _Plugin:
        pass

    inst = _Plugin()
    engine.register("step.a", lambda: CommandResult(True, "A"), plugin_instance=inst)
    engine.register("step.b", lambda: CommandResult(True, "B"), plugin_instance=inst)
    registry.register_metadata(
        "step.a", plugin="t", permission_level=PermissionLevel.LOW
    )
    registry.register_metadata(
        "step.b", plugin="t", permission_level=PermissionLevel.LOW
    )
    router = Router(
        bus, registry, [],
        safety_gate=AutoConfirmGate(bus),
        rate_limiter=RateLimiter(
            max_per_minute=1000, repeat_threshold=1000, source_overrides={}
        ),
    )
    return bus, router


def test_plan_steps_share_single_trace_id() -> None:
    bus, router = _build_router()
    executor = TaskExecutor(bus, router)

    plan_trace_ids: list[str] = []
    step_trace_ids: list[str] = []

    def on_plan_started(envelope: dict) -> None:
        tid = (envelope.get("payload") or {}).get("trace_id")
        if tid:
            plan_trace_ids.append(tid)

    def on_step(envelope: dict) -> None:
        tid = (envelope.get("payload") or {}).get("trace_id")
        if tid:
            step_trace_ids.append(tid)

    bus.subscribe("plan.started", on_plan_started)
    bus.subscribe("plan.step.started", on_step)
    bus.subscribe("plan.step.completed", on_step)

    plan = TaskPlan(
        description="two-step demo",
        steps=[TaskStep(action="step.a"), TaskStep(action="step.b")],
    )
    report = executor.execute(plan)
    assert report.success

    assert len(plan_trace_ids) == 1
    single = plan_trace_ids[0]
    assert step_trace_ids, "expected step events"
    assert all(t == single for t in step_trace_ids), (
        f"trace_ids drift within plan: {step_trace_ids!r}"
    )
