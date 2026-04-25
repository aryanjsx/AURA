"""Unit tests for file operations: create, delete, rename, move, search.

Uses real filesystem (tmp_path) — no mocking of the FS layer.
"""
from __future__ import annotations

import pytest


@pytest.mark.unit
class TestFileCreate:
    def test_file_create_new_file_exists_on_disk(self, executor, sandbox_dir):
        result = executor["file.create"]("hello.txt")
        assert (sandbox_dir / "hello.txt").exists()

    def test_file_create_existing_file_returns_warning_not_overwrite(
        self, executor, sandbox_dir
    ):
        (sandbox_dir / "exists.txt").write_text("original", encoding="utf-8")
        result = executor["file.create"]("exists.txt")
        assert "WARNING" in result.message or "already exists" in result.message
        assert (sandbox_dir / "exists.txt").read_text(encoding="utf-8") == "original"

    def test_file_create_returns_success_true(self, executor, sandbox_dir):
        result = executor["file.create"]("new_file.txt")
        assert result.success is True


@pytest.mark.unit
class TestFileDelete:
    def test_file_delete_existing_file_removes_from_disk(self, executor, sandbox_dir):
        target = sandbox_dir / "to_delete.txt"
        target.touch()
        executor["file.delete"]("to_delete.txt")
        assert not target.exists()

    def test_file_delete_nonexistent_file_returns_graceful_error(
        self, executor, sandbox_dir
    ):
        from aura.core.errors import SandboxError
        with pytest.raises(SandboxError):
            executor["file.delete"]("ghost.txt")

    def test_file_delete_returns_success_false_on_missing(
        self, executor, sandbox_dir
    ):
        from aura.core.errors import SandboxError
        with pytest.raises(SandboxError):
            executor["file.delete"]("no_such_file.txt")


@pytest.mark.unit
class TestFileRename:
    def test_file_rename_old_gone_new_exists(self, executor, sandbox_dir):
        (sandbox_dir / "old.txt").touch()
        executor["file.rename"]("old.txt", "new.txt")
        assert not (sandbox_dir / "old.txt").exists()
        assert (sandbox_dir / "new.txt").exists()

    def test_file_rename_nonexistent_source_returns_error(
        self, executor, sandbox_dir
    ):
        from aura.core.errors import SandboxError
        with pytest.raises(SandboxError):
            executor["file.rename"]("nonexistent.txt", "target.txt")


@pytest.mark.unit
class TestFileMove:
    def test_file_move_file_appears_at_destination(self, executor, sandbox_dir):
        (sandbox_dir / "moveme.txt").touch()
        dest_dir = sandbox_dir / "subdir"
        dest_dir.mkdir()
        executor["file.move"]("moveme.txt", "subdir")
        assert (dest_dir / "moveme.txt").exists()

    def test_file_move_source_no_longer_exists(self, executor, sandbox_dir):
        (sandbox_dir / "gone.txt").touch()
        (sandbox_dir / "dest").mkdir()
        executor["file.move"]("gone.txt", "dest")
        assert not (sandbox_dir / "gone.txt").exists()

    def test_file_move_autocreates_destination_directory(
        self, executor, sandbox_dir
    ):
        (sandbox_dir / "auto.txt").touch()
        result = executor["file.move"]("auto.txt", "new_sub/auto.txt")
        assert result.success is True


@pytest.mark.unit
class TestFileSearch:
    def test_file_search_returns_matching_files(self, executor, sandbox_dir):
        (sandbox_dir / "match_a.txt").touch()
        (sandbox_dir / "match_b.txt").touch()
        (sandbox_dir / "other.log").touch()
        result = executor["file.search"](".", "*.txt")
        assert len(result.data["matches"]) >= 2

    def test_file_search_zero_results_returns_clean_response(
        self, executor, sandbox_dir
    ):
        result = executor["file.search"](".", "*.nonexistent")
        assert result.success is True
        assert len(result.data["matches"]) == 0
        assert "No files found" in result.message


@pytest.mark.unit
class TestFilePathEdgeCases:
    def test_file_path_with_spaces_works_correctly(self, executor, sandbox_dir):
        result = executor["file.create"]("file with spaces.txt")
        assert (sandbox_dir / "file with spaces.txt").exists()

    def test_file_path_with_special_characters_works_correctly(
        self, executor, sandbox_dir
    ):
        result = executor["file.create"]("file-name_v2.0.txt")
        assert (sandbox_dir / "file-name_v2.0.txt").exists()
