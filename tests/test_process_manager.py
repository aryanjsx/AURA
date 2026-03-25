# Phase 1 tests — run with: pytest tests/

"""Unit tests for command_engine.process_manager."""

from __future__ import annotations

import sys

from command_engine.process_manager import (
    list_running_processes,
    run_shell_command,
)
from core.result import CommandResult


class TestRunShellCommand:
    """Tests for run_shell_command()."""

    def test_echo_hello(self) -> None:
        result = run_shell_command("echo hello")

        assert isinstance(result, CommandResult)
        assert result.success is True
        assert result.data is not None
        assert result.data["returncode"] == 0
        assert "hello" in result.data["stdout"].lower()

    def test_python_version(self) -> None:
        result = run_shell_command(f"{sys.executable} --version")

        assert result.success is True
        assert result.data is not None
        assert result.data["returncode"] == 0
        assert "python" in result.data["stdout"].lower()

    def test_invalid_command(self) -> None:
        result = run_shell_command("aura_nonexistent_cmd_xyz")

        assert isinstance(result, CommandResult)
        assert result.success is False

    def test_blocked_command_rejected(self) -> None:
        result = run_shell_command("rm -rf /")

        assert result.success is False
        assert "Blocked" in result.message


class TestListProcesses:
    """Tests for list_running_processes()."""

    def test_returns_command_result(self) -> None:
        result = list_running_processes()

        assert isinstance(result, CommandResult)
        assert result.success is True
        assert result.data is not None
        assert isinstance(result.data["processes"], list)
        assert len(result.data["processes"]) > 0

    def test_process_dict_keys(self) -> None:
        result = list_running_processes(limit=1)
        entry = result.data["processes"][0]

        assert "pid" in entry
        assert "name" in entry
        assert "cpu_percent" in entry
        assert "memory_mb" in entry

    def test_respects_limit(self) -> None:
        result = list_running_processes(limit=5)

        assert len(result.data["processes"]) <= 5
