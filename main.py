"""
AURA — CLI entry point.

Boot sequence (HARDENED):

1. Load + validate configuration (fails hard on missing required keys).
2. Acquire the event-bus singleton.
3. Configure the structured logger and attach it to the bus.
4. Install centralised error subscribers + audit-log subscriber.
5. Spawn the isolated execution worker (:mod:`aura.worker`) and receive
   its advertised action schema.
6. Build the :class:`CommandRegistry` with :class:`WorkerClient` as its
   dispatcher; import action metadata from the worker's schema.
7. Create the router with per-source rate limiter, permission
   validator, non-blocking safety gate, and the in-process intent
   parsers (:mod:`aura.intents`).
8. Run either a one-shot command (``python main.py "cpu"``) or the REPL.

Isolation invariants
--------------------
The main process NEVER imports ``plugins.*``.  A compromised plugin
therefore cannot reach the event bus, the audit log, the rate limiter,
or the safety gate of the main process — it can only corrupt its own
worker, which the client will respawn on crash.
"""

from __future__ import annotations

import atexit
import sys
from pathlib import Path

import os

from aura.core.audit_events import get_audit_event_registry
from aura.core.audit_log import AuditLogger
from aura.core.command_registry import CommandRegistry
from aura.core.config_loader import get as get_config
from aura.core.config_loader import load_config
from aura.core.error_handler import handle_error, install_default_subscribers
from aura.core.errors import AuraError
from aura.core.event_bus import get_event_bus
from aura.core.io import InputSource, OutputSink, StdinInput, StdoutOutput
from aura.core.logger import attach_event_bus_logger, get_logger
from aura.core.permissions import PermissionLevel, PermissionValidator
from aura.core.plugin_manifest import (
    PluginManifest,
    default_manifest_path,
    manifest_sha256,
)
from aura.core.rate_limiter import RateLimiter
from aura.core.router import Router
from aura.core.safety_gate import AutoConfirmGate, SafetyGate
from aura.core.worker_client import WorkerClient
from aura.intents import default_intent_parsers

_PROJECT_ROOT = Path(__file__).resolve().parent

BANNER = r"""
    ___   __  ______  ___
   /   | / / / / __ \/   |
  / /| |/ / / / /_/ / /| |
 / ___ / /_/ / _, _/ ___ |
/_/  |_\____/_/ |_/_/  |_|

Autonomous Utility & Resource Assistant
"""


def _build_help(registry: CommandRegistry) -> str:
    lines = ["Available commands:"]
    for entry in sorted(registry.list(), key=lambda e: e["action"]):
        flag = " [destructive]" if entry["destructive"] else ""
        level = entry.get("permission_level", "?")
        desc = entry["description"] or ""
        lines.append(
            f"  {entry['action']:<18} [{entry['plugin']}] "
            f"({level})  {desc}{flag}"
        )
    lines.append("\nType 'exit' or 'quit' to leave, 'help' to repeat this list.")
    return "\n".join(lines)


def bootstrap(
    *,
    auto_confirm: bool | None = None,
) -> tuple[Router, CommandRegistry]:
    """Build and wire every subsystem.  Fails fast on misconfiguration.

    **Lockdown note**: the worker is deliberately NOT returned.  The
    only supported execution path is ``Router → CommandRegistry.execute
    → Dispatcher → Worker``.  Exposing the worker to the caller would
    re-open the very backdoor the Phase-2 lockdown eliminated.
    """
    load_config()

    bus = get_event_bus()
    logger = get_logger("aura")
    attach_event_bus_logger(bus, logger)
    install_default_subscribers(bus, logger)

    audit = AuditLogger(bus)
    audit.subscribe()

    # Load the plugin safety manifest BEFORE spawning the worker.  We
    # bind its SHA-256 to the worker via an environment variable so
    # the worker can refuse to start if its local manifest differs.
    manifest_path = default_manifest_path(_PROJECT_ROOT)
    manifest = PluginManifest.load(manifest_path)
    manifest_hash = manifest_sha256(manifest_path)
    os.environ["AURA_MANIFEST_SHA256"] = manifest_hash

    worker = WorkerClient(bus, project_root=_PROJECT_ROOT)
    # Pass the hash down so it lands in the worker's restricted env
    # regardless of the caller's own environment.
    worker._bind_manifest_for_worker(manifest_path)
    schema = worker.start()
    atexit.register(worker.shutdown)

    audit_events = get_audit_event_registry()

    registry = CommandRegistry(bus, worker, manifest=manifest)
    for entry in schema:
        action = entry["action"]
        plugin_name = entry.get("plugin", "system")
        destructive = bool(entry.get("destructive", False))
        level = PermissionLevel.parse(entry.get("permission_level", "MEDIUM"))

        manifest_entry = manifest.check(
            plugin=plugin_name,
            action=action,
            permission_level=level,
            destructive=destructive,
        )
        audit_events.register_action_coverage(
            action, manifest_entry.audit_events
        )
        if destructive:
            audit_events.require_coverage(action)

        registry.register_metadata(
            action,
            plugin=plugin_name,
            description=entry.get("description", ""),
            destructive=destructive,
            permission_level=level,
        )

    # Re-subscribe the audit logger now that plugin-specific events
    # may have been registered (idempotent per-event).
    audit.subscribe()

    if auto_confirm is None:
        auto_confirm = bool(get_config("safety.auto_confirm", False))

    safety_gate: SafetyGate = (
        AutoConfirmGate(bus) if auto_confirm else SafetyGate(bus)
    )
    rate_limiter = RateLimiter()
    permission_validator = PermissionValidator()

    router = Router(
        bus,
        registry,
        default_intent_parsers(),
        safety_gate=safety_gate,
        permission_validator=permission_validator,
        rate_limiter=rate_limiter,
        auto_confirm=auto_confirm,
    )
    return router, registry


def run_repl(
    router: Router,
    registry: CommandRegistry,
    *,
    input_source: InputSource | None = None,
    output_sink: OutputSink | None = None,
) -> None:
    src = input_source or StdinInput()
    sink = output_sink or StdoutOutput()

    sink.send(BANNER)
    sink.send(_build_help(registry))

    while True:
        text = src.get_command()
        if text is None:
            sink.send("\nExiting AURA.")
            return
        if not text:
            continue
        low = text.lower()
        if low in ("exit", "quit"):
            sink.send("Goodbye.")
            return
        if low == "help":
            sink.send(_build_help(registry))
            continue
        result = router.route(text, source="cli")
        sink.send(result.message)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    auto_confirm_flag = False
    if "--yes" in argv:
        auto_confirm_flag = True
        argv = [a for a in argv if a != "--yes"]

    try:
        router, registry = bootstrap(auto_confirm=auto_confirm_flag or None)
    except AuraError as exc:
        result = handle_error(exc, context={"phase": "bootstrap"})
        print(result.message, file=sys.stderr)
        return 2

    if argv:
        text = " ".join(argv)
        result = router.route(text, source="cli")
        print(result.message)
        return 0 if result.success else 1

    try:
        run_repl(router, registry)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
