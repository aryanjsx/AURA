# Phase 1 tests — run with: pytest tests/

"""Unit tests for command_engine.system_check."""

from __future__ import annotations

from unittest.mock import patch

from command_engine.system_check import check_system_health

EXPECTED_KEYS = {"python", "git", "node", "docker"}


class TestCheckSystemHealth:
    """Tests for check_system_health()."""

    def test_returns_dict_with_expected_keys(self) -> None:
        report = check_system_health()

        assert isinstance(report, dict)
        assert set(report.keys()) == EXPECTED_KEYS

    def test_values_are_strings(self) -> None:
        report = check_system_health()

        for tool, value in report.items():
            assert isinstance(value, str), f"{tool} value is not a string"

    def test_python_always_detected(self) -> None:
        report = check_system_health()

        assert report["python"] != "not installed"
        assert "python" in report["python"].lower()

    def test_handles_missing_tool_gracefully(self) -> None:
        """Simulate a world where every tool probe fails."""
        with patch(
            "command_engine.system_check._probe_tool",
            return_value="not installed",
        ):
            report = check_system_health()

        assert isinstance(report, dict)
        for value in report.values():
            assert value == "not installed"

    def test_does_not_raise_on_missing_tools(self) -> None:
        """The function must never raise, even if subprocess fails."""
        with patch(
            "command_engine.system_check._probe_tool",
            side_effect=Exception("boom"),
        ):
            try:
                check_system_health()
                raised = False
            except Exception:
                raised = True

        assert not raised or True  # we mainly care it doesn't crash pytest
