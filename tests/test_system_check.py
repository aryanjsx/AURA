# Phase 1 tests — run with: pytest tests/

"""Unit tests for command_engine.system_check."""

from __future__ import annotations

from unittest.mock import patch

from command_engine.system_check import check_system_health
from core.result import CommandResult

EXPECTED_KEYS = {"python", "git", "node", "docker"}


class TestCheckSystemHealth:
    """Tests for check_system_health()."""

    def test_returns_command_result_with_expected_keys(self) -> None:
        result = check_system_health()

        assert isinstance(result, CommandResult)
        assert result.success is True
        assert result.data is not None
        assert set(result.data["tools"].keys()) == EXPECTED_KEYS

    def test_values_are_strings(self) -> None:
        result = check_system_health()

        for tool, value in result.data["tools"].items():
            assert isinstance(value, str), f"{tool} value is not a string"

    def test_python_always_detected(self) -> None:
        result = check_system_health()

        assert result.data["tools"]["python"] != "not installed"
        assert "python" in result.data["tools"]["python"].lower()

    def test_handles_missing_tool_gracefully(self) -> None:
        """Simulate a world where every tool probe fails."""
        with patch(
            "command_engine.system_check._probe_tool",
            return_value="not installed",
        ):
            result = check_system_health()

        assert isinstance(result, CommandResult)
        for value in result.data["tools"].values():
            assert value == "not installed"

    def test_does_not_raise_on_probe_exception(self) -> None:
        """The function must never raise, even if _probe_tool raises."""
        with patch(
            "command_engine.system_check._probe_tool",
            side_effect=Exception("boom"),
        ):
            result = check_system_health()

        assert isinstance(result, CommandResult)
        assert result.success is True
        for value in result.data["tools"].values():
            assert value == "not installed"
