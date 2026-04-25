"""Unit tests for the log reader (log.show action).

Protects: tail-N behaviour, custom line counts, missing files,
encoding errors, and empty files.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.mark.unit
class TestLogShow:
    def _make_log(self, tmp_path: Path, n_lines: int) -> Path:
        log = tmp_path / "test.log"
        log.write_text(
            "\n".join(f"line {i}" for i in range(1, n_lines + 1)) + "\n",
            encoding="utf-8",
        )
        return log

    def test_show_logs_returns_last_20_lines_by_default(
        self, executor, tmp_path
    ):
        log = self._make_log(tmp_path, 50)
        result = executor["log.show"](str(log))
        assert result.success is True
        assert result.data["lines_shown"] == 20

    def test_show_logs_returns_exactly_n_lines_when_specified(
        self, executor, tmp_path
    ):
        log = self._make_log(tmp_path, 50)
        result = executor["log.show"](str(log), lines=10)
        assert result.data["lines_shown"] == 10

    def test_show_logs_nonexistent_file_returns_graceful_error(
        self, executor, tmp_path
    ):
        fake = str(tmp_path / "nonexistent.log")
        result = executor["log.show"](fake)
        assert result.success is False
        assert "not found" in result.message.lower()

    def test_show_logs_handles_encoding_errors_without_crash(
        self, executor, tmp_path
    ):
        log = tmp_path / "binary.log"
        log.write_bytes(b"\xff\xfe" + b"valid line\n" * 5)
        result = executor["log.show"](str(log))
        assert result.success is True

    def test_show_logs_empty_file_returns_clean_response(
        self, executor, tmp_path
    ):
        log = tmp_path / "empty.log"
        log.touch()
        result = executor["log.show"](str(log))
        assert result.success is True
        assert result.data["lines_shown"] == 0
