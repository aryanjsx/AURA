"""
Phase-2 hardening: oversized parameter values must be rejected BEFORE
logging / IPC / execution.  This is the DoS-protection layer.
"""
from __future__ import annotations

import pytest

from aura.core.command_registry import CommandRegistry
from aura.core.errors import SchemaError
from aura.core.event_bus import EventBus
from aura.core.execution_engine import ExecutionEngine
from aura.core.param_schema import (
    MAX_PARAM_STRING_LEN,
    MAX_PARAMS_KEYS,
    MAX_PARAMS_SERIALISED_BYTES,
    enforce_param_size,
    validate_params,
)
from aura.core.permissions import PermissionLevel
from aura.core.plugin_manifest import PluginManifest
from aura.core.result import CommandResult
from aura.core.schema import CommandSpec


# ------------------------------------------------------------------
# Unit: enforce_param_size
# ------------------------------------------------------------------
def test_oversized_string_rejected():
    oversized = "x" * (MAX_PARAM_STRING_LEN + 1)
    with pytest.raises(SchemaError) as excinfo:
        enforce_param_size("file.create", {"path": oversized})
    assert "exceeds" in str(excinfo.value)


def test_right_at_limit_accepted():
    at_limit = "x" * MAX_PARAM_STRING_LEN
    enforce_param_size("file.create", {"path": at_limit})  # no raise


def test_oversized_serialised_payload_rejected():
    # Many medium strings whose combined serialised size exceeds the cap.
    per = (MAX_PARAMS_SERIALISED_BYTES // 8) + 1
    params = {f"k{i}": "x" * per for i in range(10)}
    with pytest.raises(SchemaError) as excinfo:
        enforce_param_size("process.shell", params)
    assert "Serialised params" in str(excinfo.value) or "exceed" in str(excinfo.value)


def test_too_many_keys_rejected():
    params = {f"k{i}": i for i in range(MAX_PARAMS_KEYS + 1)}
    with pytest.raises(SchemaError) as excinfo:
        enforce_param_size("anything", params)
    assert "Too many parameters" in str(excinfo.value)


def test_oversized_bytes_rejected():
    blob = b"\x00" * (MAX_PARAM_STRING_LEN + 1)
    with pytest.raises(SchemaError):
        enforce_param_size("anything", {"blob": blob})


# ------------------------------------------------------------------
# Integration: registry.execute rejects oversized payload before
# dispatching — handler never runs.
# ------------------------------------------------------------------
def test_registry_rejects_oversized_param_before_dispatch():
    bus = EventBus()
    engine = ExecutionEngine(bus)
    registry = CommandRegistry(
        bus, engine,
        manifest=PluginManifest.permissive(),
        auto_confirm=True,
    )

    called: list[str] = []

    def _handler(path: str):
        called.append(path)
        return CommandResult(True, "ok")

    class _Owner:
        pass

    engine.register("file.create", _handler, plugin_instance=_Owner())
    registry.register_metadata(
        "file.create", plugin="t", permission_level=PermissionLevel.MEDIUM,
    )

    oversized = "/tmp/" + "x" * (MAX_PARAM_STRING_LEN + 1)
    with pytest.raises(SchemaError):
        registry.execute(
            CommandSpec(
                action="file.create",
                params={"path": oversized},
                requires_confirm=False,
            ),
            source="cli",
        )
    assert called == []  # handler MUST not run


# ------------------------------------------------------------------
# validate_params delegates to enforce_param_size even for actions with
# no declared schema (opt-in coverage still applies size limits).
# ------------------------------------------------------------------
def test_validate_params_enforces_size_for_unknown_action():
    with pytest.raises(SchemaError):
        validate_params(
            "experimental.action",
            {"data": "x" * (MAX_PARAM_STRING_LEN + 1)},
        )
