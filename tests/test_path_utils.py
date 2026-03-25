# Phase 1 tests — run with: pytest tests/

"""Unit tests for command_engine.path_utils."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

from command_engine.path_utils import resolve_path, validate_not_protected


class TestResolvePath:
    """Tests for resolve_path()."""

    def test_resolves_relative_path(self) -> None:
        result = resolve_path("hello.txt")
        assert result.is_absolute()
        assert result.name == "hello.txt"

    def test_resolves_tilde(self) -> None:
        result = resolve_path("~/test_aura_resolve.txt")
        assert result.is_absolute()
        assert str(Path.home()) in str(result)

    def test_strips_quotes(self) -> None:
        result = resolve_path('"hello.txt"')
        assert result.name == "hello.txt"

    def test_empty_path_raises(self) -> None:
        try:
            resolve_path("")
            assert False, "Expected ValueError"
        except ValueError as e:
            assert "Empty" in str(e)

    def test_whitespace_only_raises(self) -> None:
        try:
            resolve_path("   ")
            assert False, "Expected ValueError"
        except ValueError as e:
            assert "Empty" in str(e)

    def test_smart_location_desktop(self) -> None:
        result = resolve_path("desktop/file.txt")
        expected_parent = Path.home() / "Desktop"
        assert str(expected_parent) in str(result)

    def test_smart_location_downloads(self) -> None:
        result = resolve_path("downloads/report.pdf")
        expected_parent = Path.home() / "Downloads"
        assert str(expected_parent) in str(result)

    def test_creates_parents_when_requested(self, tmp_path: Path) -> None:
        deep = tmp_path / "a" / "b" / "c" / "file.txt"
        result = resolve_path(str(deep), create_parents=True)
        assert deep.parent.exists()


class TestValidateNotProtected:
    """Tests for validate_not_protected()."""

    def test_safe_path_returns_none(self, tmp_path: Path) -> None:
        safe = tmp_path / "safe_file.txt"
        result = validate_not_protected(safe)
        assert result is None

    def test_protected_windows_path(self) -> None:
        fake = Path("C:/Windows/System32/dangerous.dll")
        result = validate_not_protected(fake)
        if sys.platform == "win32":
            assert result is not None
            assert "Blocked" in result

    def test_filesystem_root_blocked(self) -> None:
        if sys.platform == "win32":
            root = Path("C:/")
        else:
            root = Path("/")
        result = validate_not_protected(root)
        assert result is not None
        assert "root" in result.lower()

    def test_nested_protected_path_blocked(self) -> None:
        """Anything inside a protected directory should be blocked."""
        with patch(
            "command_engine.path_utils._PROTECTED_ROOTS",
            frozenset({Path("/fake_protected")}),
        ):
            nested = Path("/fake_protected/deep/inside/file.txt")
            result = validate_not_protected(nested)
            if sys.platform != "win32":
                assert result is not None
                assert "Blocked" in result

    def test_unrelated_path_not_blocked(self) -> None:
        with patch(
            "command_engine.path_utils._PROTECTED_ROOTS",
            frozenset({Path("/fake_protected")}),
        ):
            unrelated = Path("/totally/different/path.txt")
            result = validate_not_protected(unrelated)
            if sys.platform != "win32":
                assert result is None
