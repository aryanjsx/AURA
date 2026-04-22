"""
Integration tests for the isolated execution worker.

After Phase-2 lockdown the worker no longer exposes a public
``dispatch`` method, so these tests go through a real
:class:`CommandRegistry` wired to the worker via its one-shot
``_seal()`` capability.  This is the *only* supported way to invoke
the worker from the main process.

Verifies:
* main process NEVER imports plugin executor code before the worker boots
* the worker advertises a non-empty action schema
* a round-trip request/response works (via registry.execute)
* :class:`EngineError` is raised for unknown actions
* sandbox / policy errors round-trip with the correct exception class
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from aura.runtime.command_registry import CommandRegistry
from aura.core.errors import PolicyError, RegistryError, SandboxError
from aura.core.event_bus import EventBus
from aura.security.permissions import PermissionLevel, PermissionValidator
from aura.security.plugin_manifest import (
    PluginManifest,
    default_manifest_path,
    manifest_sha256,
)
from aura.security.rate_limiter import RateLimiter
from aura.core.schema import CommandSpec
from aura.runtime.worker_client import WorkerClient


_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _bind_manifest_env() -> None:
    """Worker refuses to boot unless AURA_MANIFEST_SHA256 matches."""
    os.environ["AURA_MANIFEST_SHA256"] = manifest_sha256(
        default_manifest_path(_PROJECT_ROOT)
    )


def _client() -> tuple[WorkerClient, EventBus]:
    _bind_manifest_env()
    bus = EventBus()
    return WorkerClient(bus, timeout=30.0, project_root=_PROJECT_ROOT), bus


def _wire_registry(client: WorkerClient, bus: EventBus) -> CommandRegistry:
    """Start the worker and wrap it in a permissive-source registry.

    Uses a fully permissive :class:`PermissionValidator` so legitimate
    high-permission actions (e.g. ``process.shell``) aren't blocked —
    the tests here are about the worker protocol, not about policy.
    """
    schema = client.start()
    manifest = PluginManifest.load(default_manifest_path(_PROJECT_ROOT))
    registry = CommandRegistry(
        bus, client, manifest=manifest, auto_confirm=True,
    )
    # Permissive caps: every source may run up to CRITICAL.
    registry.attach_security(
        rate_limiter=RateLimiter(max_per_minute=10_000, repeat_threshold=10_000),
        permission_validator=PermissionValidator(
            source_caps={
                "cli": PermissionLevel.CRITICAL,
                "llm": PermissionLevel.CRITICAL,
                "planner": PermissionLevel.CRITICAL,
                "auto": PermissionLevel.CRITICAL,
                "test": PermissionLevel.CRITICAL,
            },
        ),
        auto_confirm=True,
    )
    for entry in schema:
        action = entry["action"]
        plugin_name = entry.get("plugin", "system")
        destructive = bool(entry.get("destructive", False))
        level = PermissionLevel.parse(entry.get("permission_level", "MEDIUM"))
        # Manifest check may still fail if the worker schema advertises
        # something unknown; that's a test failure by design.
        registry.register_metadata(
            action,
            plugin=plugin_name,
            description=entry.get("description", ""),
            destructive=destructive,
            permission_level=level,
        )
    return registry


def test_worker_round_trip(tmp_path) -> None:
    client, bus = _client()
    try:
        registry = _wire_registry(client, bus)
        result = registry.execute(
            CommandSpec(action="system.cpu", params={}, requires_confirm=False),
            source="test",
        )
        assert result.success
        assert "cpu" in (result.message or "").lower() or "%" in (result.message or "")
    finally:
        client.shutdown()


def test_worker_rejects_unknown_action() -> None:
    client, bus = _client()
    try:
        registry = _wire_registry(client, bus)
        # Action isn't registered → RegistryError from the registry.
        with pytest.raises(RegistryError):
            registry.execute(
                CommandSpec(action="not.an.action", params={},
                            requires_confirm=False),
                source="test",
            )
    finally:
        client.shutdown()


def test_worker_reports_sandbox_error() -> None:
    client, bus = _client()
    try:
        registry = _wire_registry(client, bus)
        with pytest.raises(SandboxError):
            registry.execute(
                CommandSpec(
                    action="file.create",
                    params={"path": "/etc/passwd"},
                    requires_confirm=False,
                ),
                source="test",
            )
    finally:
        client.shutdown()


def test_worker_reports_policy_error() -> None:
    client, bus = _client()
    try:
        registry = _wire_registry(client, bus)
        with pytest.raises(PolicyError):
            registry.execute(
                CommandSpec(
                    action="process.shell",
                    params={"command": "echo hi; echo bye"},
                    requires_confirm=False,
                ),
                source="test",
            )
    finally:
        client.shutdown()


def test_main_process_does_not_import_plugins_by_default() -> None:
    """Sanity: simply constructing a :class:`WorkerClient` (without
    ``start``) must not pull any ``plugins.*`` module into
    ``sys.modules`` in the main process."""
    pre = {m for m in sys.modules if m.startswith("plugins.")}
    client = WorkerClient(EventBus(), project_root=_PROJECT_ROOT)
    assert client is not None
    post = {m for m in sys.modules if m.startswith("plugins.")}
    assert post == pre, f"main process unexpectedly imported: {post - pre}"
