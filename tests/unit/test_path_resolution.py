"""Unit tests for path keyword expansion and sandbox resolution.

Protects: keyword prefixes (desktop, downloads, documents, home),
tilde expansion, nested paths, and out-of-sandbox rejection.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from aura.security.sandbox import expand_keywords


@pytest.mark.unit
@pytest.mark.parametrize(
    "keyword,expected_suffix",
    [
        ("desktop", "Desktop"),
        ("downloads", "Downloads"),
        ("documents", "Documents"),
        ("home", ""),
    ],
    ids=["desktop", "downloads", "documents", "home"],
)
def test_keyword_maps_to_real_directory(keyword, expected_suffix):
    expanded, was_expanded = expand_keywords(keyword)
    assert was_expanded is True
    home = str(Path.home())
    if expected_suffix:
        assert expanded == str(Path.home() / expected_suffix)
    else:
        assert expanded == home


@pytest.mark.unit
def test_tilde_expands_to_home_directory():
    expanded, was_expanded = expand_keywords("~/somefile.txt")
    assert was_expanded is True
    assert str(Path.home()) in expanded
    assert expanded.endswith("somefile.txt")


@pytest.mark.unit
def test_nested_keyword_path_resolves_correctly():
    expanded, was_expanded = expand_keywords("desktop/projects/myapp")
    assert was_expanded is True
    assert "Desktop" in expanded
    assert expanded.endswith(str(Path("projects") / "myapp"))


@pytest.mark.unit
def test_unknown_prefix_does_not_expand():
    expanded, was_expanded = expand_keywords("randomprefix/file.txt")
    assert was_expanded is False
    assert expanded == "randomprefix/file.txt"


@pytest.mark.unit
def test_absolute_path_outside_sandbox_is_blocked(sandbox_dir):
    from aura.core.errors import SandboxError
    from aura.security.sandbox import resolve_safe_path

    with pytest.raises(SandboxError):
        resolve_safe_path("C:/Windows/System32/cmd.exe")
