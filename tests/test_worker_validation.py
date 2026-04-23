"""
Phase-3 hardening: the registry strictly validates every worker reply.

A compromised worker MUST NOT be able to tunnel arbitrary data through
the registry.  The pipeline enforces (all via
``_validate_worker_reply``):

* type/shape (dict + ``type`` in {"result","error"})
* required fields present, no extras
* scalar type checks for ``success`` / ``message`` / ``data`` / ...
* action echo (``reply["action"] == requested_action``)
* id echo    (``reply["id"] == outgoing request id``)
* size cap (re-serialised JSON <= ``max_bytes``)

Each rule is tested here by swapping in a malicious ``WorkerPort``
implementation.
"""
from __future__ import annotations

from typing import Any

import pytest

from aura.core.errors import EngineError
from aura.core.event_bus import EventBus
from aura.core.result import CommandResult
from aura.core.schema import CommandSpec
from aura.runtime.command_registry import (
    CommandRegistry,
    _validate_worker_reply,
)
from aura.security.permissions import PermissionLevel
from aura.security.plugin_manifest import PluginManifest


# ---------------------------------------------------------------------
# Minimal fake WorkerPort that lets each test force an arbitrary reply.
# Critically NOT callable.
# ---------------------------------------------------------------------
class _FakePort:
    __slots__ = ("_reply", "_captured", "__weakref__")

    def __init__(self, reply: Any) -> None:
        self._reply = reply
        self._captured: dict[str, Any] | None = None

    def has(self, action: str) -> bool:  # pragma: no cover - unused
        return True

    def actions(self) -> list[dict[str, Any]]:  # pragma: no cover
        return []

    def send(self, request: dict[str, Any]) -> Any:
        self._captured = dict(request)
        reply = self._reply
        if callable(reply):
            return reply(request)
        return reply


def _build_registry(port: _FakePort) -> CommandRegistry:
    bus = EventBus()
    registry = CommandRegistry(
        bus,
        port,
        manifest=PluginManifest.permissive(),
        auto_confirm=True,
    )
    registry.register_metadata(
        "probe.low",
        plugin="t",
        permission_level=PermissionLevel.LOW,
    )
    return registry


def _well_formed_reply(action: str, request_id: str) -> dict[str, Any]:
    return {
        "type": "result",
        "id": request_id,
        "action": action,
        "success": True,
        "message": "ok",
        "data": {},
        "command_type": action,
        "error_code": None,
    }


# ---------------------------------------------------------------------
# Happy path.
# ---------------------------------------------------------------------
def test_well_formed_reply_passes_validation():
    def make_reply(req):
        return _well_formed_reply(req["action"], req["id"])

    port = _FakePort(make_reply)
    registry = _build_registry(port)
    result = registry.execute(
        CommandSpec(action="probe.low", params={}, requires_confirm=False),
        source="cli",
    )
    assert isinstance(result, CommandResult)
    assert result.success is True


# ---------------------------------------------------------------------
# 1) Missing required fields.
# ---------------------------------------------------------------------
def test_reply_missing_required_field_is_rejected():
    def make_reply(req):
        reply = _well_formed_reply(req["action"], req["id"])
        del reply["success"]  # type: ignore[arg-type]
        return reply

    port = _FakePort(make_reply)
    registry = _build_registry(port)
    with pytest.raises(EngineError, match="missing required fields"):
        registry.execute(
            CommandSpec(action="probe.low", params={},
                        requires_confirm=False),
            source="cli",
        )


# ---------------------------------------------------------------------
# 2) Extra unexpected fields.
# ---------------------------------------------------------------------
def test_reply_with_extra_fields_is_rejected():
    def make_reply(req):
        reply = _well_formed_reply(req["action"], req["id"])
        reply["evil"] = "smuggled"  # extra top-level field
        return reply

    port = _FakePort(make_reply)
    registry = _build_registry(port)
    with pytest.raises(EngineError, match="unexpected fields"):
        registry.execute(
            CommandSpec(action="probe.low", params={},
                        requires_confirm=False),
            source="cli",
        )


# ---------------------------------------------------------------------
# 3) Wrong action echo (e.g. reply belonged to a different request).
# ---------------------------------------------------------------------
def test_reply_with_wrong_action_is_rejected():
    def make_reply(req):
        reply = _well_formed_reply("wrong.action", req["id"])
        return reply

    port = _FakePort(make_reply)
    registry = _build_registry(port)
    with pytest.raises(EngineError, match="action mismatch"):
        registry.execute(
            CommandSpec(action="probe.low", params={},
                        requires_confirm=False),
            source="cli",
        )


# ---------------------------------------------------------------------
# 4) Wrong id echo.
# ---------------------------------------------------------------------
def test_reply_with_wrong_id_is_rejected():
    def make_reply(req):
        reply = _well_formed_reply(req["action"], "not-my-id")
        return reply

    port = _FakePort(make_reply)
    registry = _build_registry(port)
    with pytest.raises(EngineError, match="id mismatch"):
        registry.execute(
            CommandSpec(action="probe.low", params={},
                        requires_confirm=False),
            source="cli",
        )


# ---------------------------------------------------------------------
# 5) Non-dict reply.
# ---------------------------------------------------------------------
def test_non_dict_reply_is_rejected():
    port = _FakePort("not a dict")
    registry = _build_registry(port)
    with pytest.raises(EngineError, match="not a dict"):
        registry.execute(
            CommandSpec(action="probe.low", params={},
                        requires_confirm=False),
            source="cli",
        )


# ---------------------------------------------------------------------
# 6) Wrong type on scalar field (success must be bool).
# ---------------------------------------------------------------------
def test_reply_with_wrong_scalar_type_is_rejected():
    def make_reply(req):
        reply = _well_formed_reply(req["action"], req["id"])
        reply["success"] = "maybe"  # type: ignore[assignment]
        return reply

    port = _FakePort(make_reply)
    registry = _build_registry(port)
    with pytest.raises(EngineError, match="'success' must be bool"):
        registry.execute(
            CommandSpec(action="probe.low", params={},
                        requires_confirm=False),
            source="cli",
        )


# ---------------------------------------------------------------------
# 7) Unknown reply type.
# ---------------------------------------------------------------------
def test_reply_with_unknown_type_is_rejected():
    def make_reply(req):
        return {
            "type": "weird",
            "id": req["id"],
            "action": req["action"],
            "success": True,
            "message": "",
            "data": {},
            "command_type": req["action"],
            "error_code": None,
        }

    port = _FakePort(make_reply)
    registry = _build_registry(port)
    with pytest.raises(EngineError, match="unexpected type"):
        registry.execute(
            CommandSpec(action="probe.low", params={},
                        requires_confirm=False),
            source="cli",
        )


# ---------------------------------------------------------------------
# 8) Oversized reply.
# ---------------------------------------------------------------------
def test_oversized_reply_is_rejected_by_validator():
    # Direct unit test - the cap in the pipeline uses the same
    # validator, so forcing max_bytes small here proves the mechanism.
    reply = {
        "type": "result",
        "id": "x",
        "action": "a",
        "success": True,
        "message": "x" * 10_000,
        "data": {},
        "command_type": "a",
        "error_code": None,
    }
    with pytest.raises(EngineError, match="exceeds"):
        _validate_worker_reply(
            reply,
            expected_action="a",
            expected_id="x",
            max_bytes=1024,
        )


# ---------------------------------------------------------------------
# 9) Error envelope is strictly validated too.
# ---------------------------------------------------------------------
def test_error_envelope_strict_fields():
    from aura.core.errors import ExecutionError

    def make_reply(req):
        return {
            "type": "error",
            "id": req["id"],
            "action": req["action"],
            "error_class": "ExecutionError",
            "error_code": "EXECUTION_ERROR",
            "message": "boom",
        }

    port = _FakePort(make_reply)
    registry = _build_registry(port)
    with pytest.raises(ExecutionError):
        registry.execute(
            CommandSpec(action="probe.low", params={},
                        requires_confirm=False),
            source="cli",
        )


def test_error_envelope_missing_message_is_rejected():
    def make_reply(req):
        return {
            "type": "error",
            "id": req["id"],
            "action": req["action"],
            "error_class": "ExecutionError",
            "error_code": "EXECUTION_ERROR",
            # message missing
        }

    port = _FakePort(make_reply)
    registry = _build_registry(port)
    with pytest.raises(EngineError, match="missing required fields"):
        registry.execute(
            CommandSpec(action="probe.low", params={},
                        requires_confirm=False),
            source="cli",
        )


# ---------------------------------------------------------------------
# 10) Direct unit tests on _validate_worker_reply.
# ---------------------------------------------------------------------
def test_validator_rejects_list_for_data_field():
    bad = {
        "type": "result",
        "id": "x",
        "action": "a",
        "success": True,
        "message": "ok",
        "data": [1, 2, 3],  # must be dict
        "command_type": "a",
        "error_code": None,
    }
    with pytest.raises(EngineError, match="'data' must be dict"):
        _validate_worker_reply(
            bad, expected_action="a", expected_id="x",
            max_bytes=1_000_000,
        )


def test_validator_rejects_non_string_message():
    bad = {
        "type": "result",
        "id": "x",
        "action": "a",
        "success": True,
        "message": 42,  # not a string
        "data": {},
        "command_type": "a",
        "error_code": None,
    }
    with pytest.raises(EngineError, match="'message' must be str"):
        _validate_worker_reply(
            bad, expected_action="a", expected_id="x",
            max_bytes=1_000_000,
        )
