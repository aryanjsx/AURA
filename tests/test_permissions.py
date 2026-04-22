"""PermissionValidator tests."""
from __future__ import annotations

import pytest

from aura.core.errors import PermissionDenied
from aura.core.permissions import PermissionLevel, PermissionValidator


def test_cli_can_run_critical():
    v = PermissionValidator()
    v.validate(action="shell.run", level=PermissionLevel.CRITICAL, source="cli")


def test_llm_blocked_from_high_and_critical():
    v = PermissionValidator()
    with pytest.raises(PermissionDenied):
        v.validate(action="file.delete", level=PermissionLevel.HIGH, source="llm")
    with pytest.raises(PermissionDenied):
        v.validate(action="shell.run", level=PermissionLevel.CRITICAL, source="llm")


def test_llm_allowed_for_low_and_medium():
    v = PermissionValidator()
    v.validate(action="cpu", level=PermissionLevel.LOW, source="llm")
    v.validate(action="file.create", level=PermissionLevel.MEDIUM, source="llm")


def test_planner_capped_at_high():
    v = PermissionValidator()
    v.validate(action="file.delete", level=PermissionLevel.HIGH, source="planner")
    with pytest.raises(PermissionDenied):
        v.validate(action="shell.run", level=PermissionLevel.CRITICAL, source="planner")


def test_unknown_source_defaults_to_low():
    v = PermissionValidator()
    v.validate(action="cpu", level=PermissionLevel.LOW, source="mystery")
    with pytest.raises(PermissionDenied):
        v.validate(action="cpu", level=PermissionLevel.MEDIUM, source="mystery")


def test_permission_level_parsing():
    assert PermissionLevel.parse("low") is PermissionLevel.LOW
    assert PermissionLevel.parse("CRITICAL") is PermissionLevel.CRITICAL
    with pytest.raises(ValueError):
        PermissionLevel.parse("extreme")
