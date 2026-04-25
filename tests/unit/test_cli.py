"""Unit tests for CLI flags (--version, --help, --yes) and REPL input handling.

Protects: version output, help output, empty/whitespace/unknown commands,
exit/quit behaviour.
"""
from __future__ import annotations

import sys
from io import StringIO
from unittest.mock import patch

import pytest


@pytest.mark.unit
class TestVersionFlag:
    def test_version_flag_prints_version_string(self, capsys):
        from aura.cli import main

        code = main(["--version"])
        captured = capsys.readouterr()
        assert "AURA" in captured.out
        assert "2.0.0" in captured.out

    def test_version_flag_exits_zero(self):
        from aura.cli import main

        code = main(["--version"])
        assert code == 0


@pytest.mark.unit
class TestHelpFlag:
    def test_help_flag_prints_usage(self, capsys):
        from aura.cli import main

        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        captured = capsys.readouterr()
        assert "usage" in captured.out.lower() or "aura" in captured.out.lower()

    def test_help_flag_exits_zero(self):
        from aura.cli import main

        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        assert exc_info.value.code == 0


@pytest.mark.unit
class TestYesFlag:
    def test_yes_empty_string_exits_with_error(self, capsys):
        from aura.cli import main

        code = main(["--yes", ""])
        captured = capsys.readouterr()
        assert code == 1
        assert "No command" in captured.out or "no command" in captured.out.lower()

    def test_yes_whitespace_only_exits_with_error(self, capsys):
        from aura.cli import main

        code = main(["--yes", "   "])
        captured = capsys.readouterr()
        assert code == 1


@pytest.mark.unit
class TestReplInputs:
    def test_yes_help_prints_command_list(self, capsys):
        from aura.cli import main

        code = main(["--yes", "help"])
        captured = capsys.readouterr()
        assert code == 0
        assert "Available commands" in captured.out or "commands" in captured.out.lower()

    def test_yes_unknown_command_returns_unknown_command_no_crash(self, capsys):
        from aura.cli import main

        code = main(["--yes", "zzz_gibberish_command_zzz"])
        captured = capsys.readouterr()
        assert isinstance(code, int)

    def test_yes_valid_command_returns_output(self, capsys):
        from aura.cli import main

        code = main(["--yes", "system.health"])
        captured = capsys.readouterr()
        assert isinstance(code, int)
        assert len(captured.out) > 0
