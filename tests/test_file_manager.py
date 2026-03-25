# Phase 1 tests — run with: pytest tests/

"""Unit tests for command_engine.file_manager."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from command_engine.file_manager import (
    create_file,
    delete_file,
    move_file,
    rename_file,
)
from core.result import CommandResult


class TestCreateFile:
    """Tests for create_file()."""

    def test_create_file_succeeds(self, tmp_path: Path) -> None:
        target = tmp_path / "hello.txt"
        result = create_file(str(target))

        assert isinstance(result, CommandResult)
        assert result.success is True
        assert "File created" in result.message
        assert target.exists()

    def test_create_file_nested_dirs(self, tmp_path: Path) -> None:
        target = tmp_path / "a" / "b" / "c" / "deep.txt"
        result = create_file(str(target))

        assert result.success is True
        assert "File created" in result.message
        assert target.exists()

    def test_create_file_in_protected_path(self) -> None:
        """Attempting to create a file inside a protected root should not
        crash.  The function returns a CommandResult regardless."""
        result = create_file("C:/Windows/aura_test_junk.xyz")
        assert isinstance(result, CommandResult)


class TestDeleteFile:
    """Tests for delete_file()."""

    def test_delete_existing_file(self, tmp_path: Path) -> None:
        target = tmp_path / "doomed.txt"
        target.touch()
        assert target.exists()

        result = delete_file(str(target))

        assert result.success is True
        assert "deleted" in result.message.lower()
        assert not target.exists()

    def test_delete_nonexistent_file(self, tmp_path: Path) -> None:
        target = tmp_path / "ghost.txt"
        result = delete_file(str(target))

        assert result.success is False
        assert "not found" in result.message.lower()

    def test_delete_protected_path_blocked(self) -> None:
        with patch(
            "command_engine.file_manager.validate_not_protected",
            return_value="Blocked: protected path",
        ):
            result = delete_file("/some/fake/path.txt")

        assert "Blocked" in result.message


class TestRenameFile:
    """Tests for rename_file()."""

    def test_rename_rejects_path_traversal(self, tmp_path: Path) -> None:
        src = tmp_path / "original.txt"
        src.touch()
        result = rename_file(str(src), "../../etc/evil.txt")
        assert result.success is False
        assert "filename" in result.message.lower()


class TestMoveFile:
    """Tests for move_file()."""

    def test_move_file_succeeds(self, tmp_path: Path) -> None:
        src = tmp_path / "origin.txt"
        src.write_text("data", encoding="utf-8")

        dst_dir = tmp_path / "target_dir"
        dst_dir.mkdir()
        dst = dst_dir / "origin.txt"

        result = move_file(str(src), str(dst_dir))

        assert result.success is True
        assert "Moved" in result.message
        assert dst.exists()
        assert not src.exists()

    def test_move_nonexistent_source(self, tmp_path: Path) -> None:
        src = tmp_path / "nope.txt"
        dst = tmp_path / "dest.txt"

        result = move_file(str(src), str(dst))

        assert result.success is False
        assert "not found" in result.message.lower()
