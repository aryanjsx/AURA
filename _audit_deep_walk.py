"""Bounded adversarial reachability probe.

Rather than a combinatorial walk of every method and its class mro, we
simulate what an *attacker* would do in the most optimistic scenario:
follow attributes, slots, closures, __func__, __self__ up to a large
but finite budget.  The special case we DO cover is attribute lookup
on slot-only proxies (like _ExecutorProxy) via ``getattr``.
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

_SBX = Path(tempfile.mkdtemp(prefix="aura_deep_"))
os.environ["AURA_SANDBOX_DIR"] = str(_SBX)

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from aura.core.config_loader import load_config  # noqa: E402
load_config()

from aura.core.event_bus import EventBus  # noqa: E402
from aura.core.result import CommandResult  # noqa: E402
from aura.runtime.command_registry import CommandRegistry  # noqa: E402
from aura.runtime.execution_engine import ExecutionEngine  # noqa: E402
from aura.runtime.router import Router  # noqa: E402
from aura.security.permissions import PermissionLevel  # noqa: E402
from aura.security.plugin_manifest import PluginManifest  # noqa: E402
from tests._inprocess_port import InProcessWorkerPort  # noqa: E402


def build():
    bus = EventBus()
    engine = ExecutionEngine(bus)

    class _P: pass

    engine.register("probe.low", lambda **kw: CommandResult(True, "ok"),
                    plugin_instance=_P())
    port = InProcessWorkerPort(engine)
    reg = CommandRegistry(bus, port,
                          manifest=PluginManifest.permissive(),
                          auto_confirm=True)
    reg.register_metadata("probe.low", plugin="t",
                          permission_level=PermissionLevel.LOW)
    router = Router(bus, reg)
    return router, reg, engine, port


_BORING_TYPES = (int, float, bool, str, bytes, bytearray, type(None))


def is_boring(obj):
    if isinstance(obj, _BORING_TYPES):
        return True
    if obj.__class__.__module__ == "builtins" and obj.__class__ is type:
        return True
    return False


def walk(root, name_root, budget=20000):
    seen: set[int] = set()
    out: list[tuple[str, object]] = []
    stack: list[tuple[str, object]] = [(name_root, root)]
    while stack and len(out) < budget:
        path, obj = stack.pop()
        if id(obj) in seen:
            continue
        seen.add(id(obj))
        out.append((path, obj))

        cands = []
        # instance __dict__
        try:
            d = getattr(obj, "__dict__", None)
            if isinstance(d, dict):
                cands.extend(d.items())
        except Exception:
            pass
        # slots
        slots_names: list[str] = []
        for klass in type(obj).__mro__:
            sl = getattr(klass, "__slots__", None)
            if isinstance(sl, str):
                slots_names.append(sl)
            elif isinstance(sl, (tuple, list)):
                slots_names.extend(sl)
        for s in slots_names:
            try:
                cands.append((s, getattr(obj, s)))
            except Exception:
                continue
        # For proxies, attacker would try obvious attribute names.
        for probe in ("execute", "send", "_call", "dispatch", "_dispatch",
                      "_engine", "_executor", "_worker_port",
                      "_CommandRegistry__dispatch"):
            try:
                v = getattr(obj, probe)
            except Exception:
                continue
            cands.append((f".{probe}", v))
        # For callables, inspect closure + __func__ + __self__.
        if callable(obj):
            closure = getattr(obj, "__closure__", None) or ()
            for i, cell in enumerate(closure):
                try:
                    inner = cell.cell_contents
                except ValueError:
                    continue
                cands.append((f"[closure[{i}]]", inner))
            for k in ("__func__", "__self__"):
                try:
                    v = getattr(obj, k)
                except Exception:
                    continue
                if v is obj:
                    continue
                cands.append((k, v))

        for child_name, child in cands:
            if is_boring(child):
                continue
            if id(child) in seen:
                continue
            stack.append((f"{path}.{child_name}", child))
    return out


def main():
    router, reg, engine, port = build()
    reached = walk(router, "router") + walk(reg, "registry")

    suspects = {
        "ExecutionEngine instance": lambda o: isinstance(o, ExecutionEngine),
        "InProcessWorkerPort instance":
            lambda o: isinstance(o, InProcessWorkerPort),
        "WorkerPort `send` bound method":
            lambda o: callable(o)
            and getattr(o, "__name__", "") == "send"
            and getattr(o, "__self__", None) is port,
        "engine.dispatch bound method":
            lambda o: callable(o) and getattr(o, "__name__", "") == "dispatch",
        "executors dict":
            lambda o: (isinstance(o, dict)
                       and "probe.low" in o
                       and callable(o.get("probe.low"))),
    }

    findings = {k: [] for k in suspects}
    for path, obj in reached:
        for name, pred in suspects.items():
            try:
                hit = pred(obj)
            except Exception:
                hit = False
            if hit:
                findings[name].append(path)

    print(f"DEEP WALK objects visited: {len(reached)}")
    for name, paths in findings.items():
        label = "REACHABLE" if paths else "NOT REACHABLE"
        print(f"  {label}: {name}" + (f"  ({len(paths)})" if paths else ""))
        for p in paths[:5]:
            print(f"     at: {p}")


if __name__ == "__main__":
    main()
