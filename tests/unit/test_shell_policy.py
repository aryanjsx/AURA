"""Unit tests for shell allowlist / denylist policy and source-code safety.

Protects: allowed commands pass, blocked commands rejected,
shell injection prevented, no eval/exec in source.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from aura.core.errors import PolicyError
from aura.security.policy import CommandPolicy


@pytest.fixture()
def policy():
    return CommandPolicy()


# ── allowed commands ─────────────────────────────────────────────────


@pytest.mark.unit
class TestAllowedCommands:
    def test_allowed_command_git_passes_policy(self, policy):
        policy.check_shell_command("git status")

    def test_allowed_command_npm_passes_policy(self, policy):
        policy.check_shell_command("npm --version")

    def test_allowed_command_echo_passes_policy(self, policy):
        policy.check_shell_command("echo hello world")


# ── blocked commands ─────────────────────────────────────────────────


@pytest.mark.unit
class TestBlockedCommands:
    def test_blocked_command_python_rejected(self, policy):
        with pytest.raises(PolicyError):
            policy.check_shell_command("python script.py")

    def test_blocked_command_node_rejected(self, policy):
        with pytest.raises(PolicyError):
            policy.check_shell_command("node index.js")

    def test_blocked_command_bash_rejected(self, policy):
        with pytest.raises(PolicyError):
            policy.check_shell_command("bash -c ls")

    def test_blocked_command_powershell_rejected(self, policy):
        with pytest.raises(PolicyError):
            policy.check_shell_command("powershell -command Get-Process")


# ── shell injection ──────────────────────────────────────────────────


@pytest.mark.unit
class TestShellInjection:
    def test_no_shell_injection_via_semicolon(self, policy):
        with pytest.raises(PolicyError):
            policy.check_shell_command("echo hello; rm -rf /")

    def test_no_shell_injection_via_ampersand(self, policy):
        with pytest.raises(PolicyError):
            policy.check_shell_command("echo hello && rm -rf /")


# ── source code safety ──────────────────────────────────────────────


@pytest.mark.unit
class TestSourceCodeSafety:
    """Scan all AURA source files — no eval() or exec() on dynamic input."""

    _AURA_ROOT = Path(__file__).resolve().parent.parent.parent / "aura"

    def _scan_source(self, pattern: str) -> list[tuple[str, int, str]]:
        """Scan for bare builtin calls like eval( or exec(.

        Skips matches that are part of a larger identifier name (e.g.
        _handle_exec) by requiring a non-alphanumeric/underscore char
        or start-of-line before the match.
        """
        import re
        # Match the pattern only when preceded by start-of-line or a
        # non-identifier character — rejects _handle_exec( etc.
        regex = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(pattern))
        hits: list[tuple[str, int, str]] = []
        for py in self._AURA_ROOT.rglob("*.py"):
            for lineno, line in enumerate(
                py.read_text(encoding="utf-8", errors="replace").splitlines(),
                start=1,
            ):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if regex.search(stripped):
                    hits.append((str(py.relative_to(self._AURA_ROOT)), lineno, stripped))
        return hits

    def test_no_eval_in_source_code(self):
        hits = self._scan_source("eval(")
        assert hits == [], f"eval() found in source: {hits}"

    def test_no_exec_in_source_code(self):
        hits = self._scan_source("exec(")
        assert hits == [], f"exec() found in source: {hits}"
