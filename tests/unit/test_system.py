"""Unit tests for system commands: health check, process list, run command.

Process list uses real psutil; kill is mocked. Shell commands are policy-checked.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from aura.core.errors import PolicyError


@pytest.mark.unit
class TestProcessList:
    def test_list_processes_returns_nonempty_list(self, executor):
        result = executor["process.list"]()
        assert result.success is True
        assert len(result.data["processes"]) > 0

    def test_list_processes_each_entry_has_pid_name_cpu_mem(self, executor):
        result = executor["process.list"]()
        for proc in result.data["processes"]:
            assert "pid" in proc
            assert "name" in proc
            assert "cpu_percent" in proc
            assert "memory_mb" in proc


@pytest.mark.unit
class TestHealthCheck:
    def test_health_check_includes_python_version(self, executor):
        result = executor["system.health"]()
        assert "python" in result.data["tools"] or "Python" in result.message

    def test_health_check_python_version_matches_runtime(self, executor):
        result = executor["system.health"]()
        expected_prefix = f"Python {sys.version.split()[0]}"
        assert result.data["tools"]["python"] == expected_prefix


@pytest.mark.unit
class TestRunCommand:
    def test_run_command_echo_returns_hello(self, executor):
        result = executor["process.shell"]("echo hello")
        assert result.success is True
        assert "hello" in result.message.lower()

    def test_run_command_git_version_returns_output(self, executor):
        result = executor["process.shell"]("git --version")
        assert result.success is True
        assert "git" in result.message.lower()

    def test_run_command_blocked_command_returns_policy_error(self, executor):
        with pytest.raises(PolicyError):
            executor["process.shell"]("python -c print(1)")


@pytest.mark.unit
class TestKillProcess:
    def test_kill_process_nonexistent_returns_graceful_error(self, executor):
        result = executor["process.kill"]("zzz_nonexistent_process_zzz")
        assert result.success is False
        assert "No running process" in result.message or result.data["killed"] == 0
