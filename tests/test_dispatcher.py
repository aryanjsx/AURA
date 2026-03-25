# Phase 1 tests — run with: pytest tests/

"""Unit tests for command_engine.dispatcher."""

from __future__ import annotations

from unittest.mock import patch

from command_engine.dispatcher import dispatch, execute_intent, parse_intent
from core.intent import Intent
from core.result import CommandResult


class TestParseIntent:
    """Tests for parse_intent()."""

    def test_create_file_intent(self) -> None:
        result = parse_intent("create file hello.txt")
        assert isinstance(result, Intent)
        assert result.action == "file.create"
        assert result.args == {"path": "hello.txt"}

    def test_delete_file_intent(self) -> None:
        result = parse_intent("delete file temp.log")
        assert isinstance(result, Intent)
        assert result.action == "file.delete"
        assert result.args == {"path": "temp.log"}

    def test_run_command_intent(self) -> None:
        result = parse_intent("run command echo hello")
        assert isinstance(result, Intent)
        assert result.action == "process.shell"
        assert result.args == {"command": "echo hello"}

    def test_list_processes_intent(self) -> None:
        result = parse_intent("list processes")
        assert isinstance(result, Intent)
        assert result.action == "process.list"

    def test_kill_process_intent(self) -> None:
        result = parse_intent("kill process notepad")
        assert isinstance(result, Intent)
        assert result.action == "process.kill"
        assert result.args == {"process_name": "notepad"}

    def test_system_health_intent(self) -> None:
        result = parse_intent("check system health")
        assert isinstance(result, Intent)
        assert result.action == "system.health"

    def test_create_project_intent(self) -> None:
        result = parse_intent("create project myapp")
        assert isinstance(result, Intent)
        assert result.action == "project.create"
        assert result.args == {"project_name": "myapp"}

    def test_show_logs_intent(self) -> None:
        result = parse_intent("show logs app.log 50")
        assert isinstance(result, Intent)
        assert result.action == "logs.show"
        assert result.args["file_path"] == "app.log"
        assert result.args["lines"] == 50

    def test_missing_arg_returns_command_result(self) -> None:
        result = parse_intent("create file")
        assert isinstance(result, CommandResult)
        assert result.success is False
        assert "Usage" in result.message

    def test_unknown_command_returns_fallback_intent(self) -> None:
        result = parse_intent("frobnicate everything")
        assert isinstance(result, Intent)
        assert result.action == "unknown"

    def test_search_files_intent(self) -> None:
        result = parse_intent("search files /tmp *.py")
        assert isinstance(result, Intent)
        assert result.action == "file.search"
        assert result.args["pattern"] == "*.py"

    def test_rename_file_intent(self) -> None:
        result = parse_intent("rename file old.txt new.txt")
        assert isinstance(result, Intent)
        assert result.action == "file.rename"
        assert result.args["old_name"] == "old.txt"
        assert result.args["new_name"] == "new.txt"


class TestExecuteIntent:
    """Tests for execute_intent()."""

    def test_unknown_action_returns_failure(self) -> None:
        intent = Intent(action="nonexistent.action", args={}, raw_text="nope")
        result = execute_intent(intent)

        assert isinstance(result, CommandResult)
        assert result.success is False
        assert "Unknown" in result.message

    def test_policy_blocks_dangerous_shell(self) -> None:
        intent = Intent(
            action="process.shell",
            args={"command": "rm -rf /"},
            raw_text="rm -rf /",
        )
        result = execute_intent(intent)

        assert result.success is False
        assert "Blocked" in result.message

    def test_low_confidence_llm_intent_rejected(self) -> None:
        intent = Intent(
            action="file.create",
            args={"path": "test.txt"},
            raw_text="make a file",
            source="llm",
            confidence=0.3,
        )
        result = execute_intent(intent)

        assert result.success is False
        assert "confidence" in result.message.lower()

    def test_high_confidence_llm_intent_accepted(self, tmp_path) -> None:
        target = tmp_path / "llm_file.txt"
        intent = Intent(
            action="file.create",
            args={"path": str(target)},
            raw_text="create a file",
            source="llm",
            confidence=0.9,
        )
        result = execute_intent(intent)

        assert result.success is True

    def test_argument_mismatch_returns_error(self) -> None:
        intent = Intent(
            action="file.create",
            args={"wrong_key": "oops"},
            raw_text="create file",
        )
        result = execute_intent(intent)

        assert result.success is False
        assert "Invalid arguments" in result.message or "Error" in result.message


class TestDispatch:
    """Tests for dispatch() — the CLI entry point."""

    def test_empty_command(self) -> None:
        result = dispatch("")
        assert result.success is False
        assert "No command" in result.message

    def test_whitespace_only(self) -> None:
        result = dispatch("   ")
        assert result.success is False

    def test_valid_create_file(self, tmp_path) -> None:
        target = tmp_path / "dispatched.txt"
        result = dispatch(f"create file {target}")

        assert isinstance(result, CommandResult)
        assert result.success is True
        assert target.exists()

    def test_unknown_command_does_not_crash(self) -> None:
        result = dispatch("xyzzy plugh")
        assert isinstance(result, CommandResult)
        assert result.success is False

    def test_kill_protected_process_blocked(self) -> None:
        result = dispatch("kill process svchost")
        assert result.success is False
        assert "protected" in result.message.lower() or "Blocked" in result.message
