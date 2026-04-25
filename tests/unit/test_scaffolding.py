"""Unit tests for project scaffolding.

Protects: directory creation, skeleton contents (src/, tests/, README.md,
.gitignore, requirements.txt), error handling for missing/existing paths.
"""
from __future__ import annotations

import pytest

from aura.core.errors import ExecutionError


@pytest.mark.unit
class TestProjectCreate:
    def test_create_project_directory_exists_after_creation(
        self, executor, sandbox_dir
    ):
        result = executor["project.create"]("myproject")
        assert (sandbox_dir / "myproject").is_dir()

    def test_create_project_contains_src_folder(self, executor, sandbox_dir):
        executor["project.create"]("proj_src")
        assert (sandbox_dir / "proj_src" / "src").is_dir()

    def test_create_project_contains_tests_folder(self, executor, sandbox_dir):
        executor["project.create"]("proj_tests")
        assert (sandbox_dir / "proj_tests" / "tests").is_dir()

    def test_create_project_contains_readme(self, executor, sandbox_dir):
        executor["project.create"]("proj_readme")
        assert (sandbox_dir / "proj_readme" / "README.md").exists()

    def test_create_project_contains_gitignore(self, executor, sandbox_dir):
        executor["project.create"]("proj_gi")
        assert (sandbox_dir / "proj_gi" / ".gitignore").exists()

    def test_create_project_contains_requirements_txt(
        self, executor, sandbox_dir
    ):
        executor["project.create"]("proj_req")
        assert (sandbox_dir / "proj_req" / "requirements.txt").exists()

    def test_create_project_no_path_returns_usage_hint(
        self, executor, sandbox_dir
    ):
        with pytest.raises(ExecutionError, match="[Pp]ath is required|[Uu]sage"):
            executor["project.create"]("")

    def test_create_project_existing_path_handled_gracefully(
        self, executor, sandbox_dir
    ):
        target = sandbox_dir / "existing_proj"
        target.mkdir()
        (target / "sentinel.txt").touch()
        result = executor["project.create"]("existing_proj")
        assert result.success is False or "already exists" in result.message
