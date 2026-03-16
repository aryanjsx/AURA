# Phase 1 tests — run with: pytest tests/

"""Unit tests for command_engine.process_manager."""

from __future__ import annotations

import sys

from command_engine.process_manager import (
    list_running_processes,
    run_shell_command,
)


class TestRunShellCommand:
    """Tests for run_shell_command()."""

    def test_echo_hello(self) -> None:
        result = run_shell_command("echo hello")

        assert result["returncode"] == 0
        assert "hello" in result["stdout"].lower()

    def test_python_version(self) -> None:
        result = run_shell_command(f"{sys.executable} --version")

        assert result["returncode"] == 0
        assert "python" in result["stdout"].lower()

    def test_invalid_command(self) -> None:
        result = run_shell_command("aura_nonexistent_cmd_xyz")

        assert isinstance(result, dict)
        assert "returncode" in result
        assert result["returncode"] != 0


class TestListProcesses:
    """Tests for list_running_processes()."""

    def test_returns_list(self) -> None:
        procs = list_running_processes()

        assert isinstance(procs, list)
        assert len(procs) > 0

    def test_process_dict_keys(self) -> None:
        procs = list_running_processes(limit=1)
        entry = procs[0]

        assert "pid" in entry
        assert "name" in entry
        assert "cpu_percent" in entry
        assert "memory_mb" in entry

    def test_respects_limit(self) -> None:
        procs = list_running_processes(limit=5)

        assert len(procs) <= 5
