"""
Phase-2 hardening: the dynamic :class:`AuditEventRegistry` replaces the
old hard-coded event tuple and enforces that every destructive action
has at least one audit event declared.
"""
from __future__ import annotations

import pytest

from aura.core.audit_events import (
    AuditCoverageError,
    AuditEventRegistry,
    get_audit_event_registry,
    reset_audit_event_registry,
)


def test_registry_contains_core_events():
    reg = AuditEventRegistry()
    events = reg.events()
    for core in (
        "command.executing",
        "command.completed",
        "command.destructive",
        "permission.denied",
        "rate_limit.blocked",
        "sandbox.blocked",
        "policy.blocked",
        "schema.rejected",
    ):
        assert core in events, core


def test_register_event_is_idempotent():
    reg = AuditEventRegistry()
    reg.register_event("plugin.custom")
    reg.register_event("plugin.custom")
    assert "plugin.custom" in reg.events()


def test_register_event_rejects_empty():
    reg = AuditEventRegistry()
    with pytest.raises(ValueError):
        reg.register_event("")
    with pytest.raises(ValueError):
        reg.register_event(None)  # type: ignore[arg-type]


def test_register_action_coverage_tracks_events():
    reg = AuditEventRegistry()
    reg.register_action_coverage(
        "plugin.rm", ["plugin.rm.started", "plugin.rm.completed"]
    )
    assert reg.has_coverage("plugin.rm")
    assert "plugin.rm.started" in reg.events()
    assert "plugin.rm.completed" in reg.coverage_for("plugin.rm")


def test_require_coverage_raises_when_missing():
    reg = AuditEventRegistry()
    with pytest.raises(AuditCoverageError):
        reg.require_coverage("plugin.unseen")


def test_require_coverage_passes_when_covered():
    reg = AuditEventRegistry()
    reg.register_action_coverage("plugin.x", ["plugin.x.done"])
    reg.require_coverage("plugin.x")  # no raise


def test_singleton_reset():
    reset_audit_event_registry()
    a = get_audit_event_registry()
    a.register_action_coverage("demo", ["demo.done"])
    reset_audit_event_registry()
    b = get_audit_event_registry()
    assert not b.has_coverage("demo")
