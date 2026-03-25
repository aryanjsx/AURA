# Phase 1 tests — run with: pytest tests/

"""Unit tests for core.policy."""

from __future__ import annotations

from core.intent import Intent
from core.policy import CommandPolicy, get_policy


class TestCommandPolicy:
    """Tests for CommandPolicy shell-command validation."""

    def setup_method(self) -> None:
        self.policy = CommandPolicy()

    def test_safe_command_passes(self) -> None:
        assert self.policy.check_shell_command("echo hello") is None

    def test_blocked_exact_rm_rf(self) -> None:
        result = self.policy.check_shell_command("rm -rf /")
        assert result is not None
        assert "Blocked" in result

    def test_blocked_exact_poweroff(self) -> None:
        result = self.policy.check_shell_command("poweroff")
        assert result is not None
        assert "Blocked" in result

    def test_blocked_substring_mkfs(self) -> None:
        result = self.policy.check_shell_command("mkfs.ext4 /dev/sda1")
        assert result is not None
        assert "dangerous pattern" in result

    def test_blocked_substring_dd(self) -> None:
        result = self.policy.check_shell_command("dd if=/dev/zero of=/dev/sda")
        assert result is not None
        assert "dangerous pattern" in result

    def test_blocked_format_c(self) -> None:
        result = self.policy.check_shell_command("format c:")
        assert result is not None

    def test_blocked_del_windows(self) -> None:
        result = self.policy.check_shell_command("del /s /q c:\\windows")
        assert result is not None

    def test_case_insensitive(self) -> None:
        result = self.policy.check_shell_command("RM -RF /")
        assert result is not None
        assert "Blocked" in result


class TestPolicyKillProtection:
    """Tests for kill_process policy checks."""

    def setup_method(self) -> None:
        self.policy = CommandPolicy()

    def test_safe_process_passes(self) -> None:
        assert self.policy.check_kill_target("notepad") is None

    def test_protected_svchost_blocked(self) -> None:
        result = self.policy.check_kill_target("svchost")
        assert result is not None
        assert "protected" in result.lower()

    def test_protected_explorer_blocked(self) -> None:
        result = self.policy.check_kill_target("explorer")
        assert result is not None

    def test_protected_init_blocked(self) -> None:
        result = self.policy.check_kill_target("init")
        assert result is not None

    def test_protected_systemd_blocked(self) -> None:
        result = self.policy.check_kill_target("systemd")
        assert result is not None

    def test_case_insensitive(self) -> None:
        result = self.policy.check_kill_target("SVCHOST")
        assert result is not None


class TestValidateIntent:
    """Tests for validate_intent() routing."""

    def setup_method(self) -> None:
        self.policy = CommandPolicy()

    def test_shell_intent_validated(self) -> None:
        intent = Intent(
            action="process.shell",
            args={"command": "rm -rf /"},
        )
        assert self.policy.validate_intent(intent) is not None

    def test_kill_intent_validated(self) -> None:
        intent = Intent(
            action="process.kill",
            args={"process_name": "svchost"},
        )
        assert self.policy.validate_intent(intent) is not None

    def test_safe_intent_passes(self) -> None:
        intent = Intent(
            action="file.create",
            args={"path": "test.txt"},
        )
        assert self.policy.validate_intent(intent) is None


class TestGetPolicy:
    """Tests for the singleton accessor."""

    def test_returns_command_policy(self) -> None:
        policy = get_policy()
        assert isinstance(policy, CommandPolicy)

    def test_returns_same_instance(self) -> None:
        a = get_policy()
        b = get_policy()
        assert a is b
