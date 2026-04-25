"""Unit tests for sandbox enforcement and safety gate.

Protects: out-of-sandbox blocking, protected path blocking,
confirmation accept/deny/timeout flows.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from aura.core.errors import (
    ConfirmationDenied,
    ConfirmationTimeout,
    SandboxError,
)
from aura.security.sandbox import resolve_safe_path


# ── sandbox blocks ───────────────────────────────────────────────────


@pytest.mark.unit
class TestSandboxBlocking:
    def test_sandbox_blocks_path_outside_sandbox_root(self, sandbox_dir):
        with pytest.raises(SandboxError):
            resolve_safe_path("/some/external/path")

    def test_sandbox_blocks_windows_system32(self, sandbox_dir):
        with pytest.raises(SandboxError):
            resolve_safe_path("C:/Windows/System32/cmd.exe")

    def test_sandbox_blocks_usr_directory(self, sandbox_dir):
        with pytest.raises(SandboxError):
            resolve_safe_path("/usr/bin/ls")

    def test_sandbox_blocks_etc_directory(self, sandbox_dir):
        with pytest.raises(SandboxError):
            resolve_safe_path("/etc/passwd")

    def test_sandbox_blocks_program_files(self, sandbox_dir):
        with pytest.raises(SandboxError):
            resolve_safe_path("C:/Program Files/something")


# ── safety gate ──────────────────────────────────────────────────────


@pytest.mark.unit
class TestSafetyGate:
    def _make_gate(self, input_fn, timeout=2.0):
        from aura.core.event_bus import EventBus
        from aura.security.safety_gate import SafetyGate

        bus = EventBus()
        return SafetyGate(bus, input_fn=input_fn, timeout=timeout)

    def test_safety_gate_cancels_on_no_confirmation(self):
        gate = self._make_gate(input_fn=lambda _: "no")
        with pytest.raises(ConfirmationDenied):
            gate.request(
                action="file.delete",
                params={},
                source="cli",
                permission="HIGH",
            )

    def test_safety_gate_cancels_on_timeout(self):
        def slow_input(_):
            import time
            time.sleep(5)
            return "yes"

        gate = self._make_gate(input_fn=slow_input, timeout=0.1)
        with pytest.raises(ConfirmationTimeout):
            gate.request(
                action="file.delete",
                params={},
                source="cli",
                permission="HIGH",
            )

    def test_safety_gate_proceeds_on_yes_confirmation(self):
        gate = self._make_gate(input_fn=lambda _: "yes")
        gate.request(
            action="file.delete",
            params={},
            source="cli",
            permission="HIGH",
        )

    def test_safety_gate_proceeds_on_confirm_confirmation(self):
        gate = self._make_gate(input_fn=lambda _: "confirm")
        gate.request(
            action="file.delete",
            params={},
            source="cli",
            permission="HIGH",
        )
