"""Unit tests for project scaffolding.

Protects: multi-stack project creation (python, node, react, fastapi),
stack-specific file generation, default stack behaviour, error handling
for missing/existing paths, and unknown stack rejection.
"""
from __future__ import annotations

import pytest

from aura.core.errors import ExecutionError


@pytest.mark.unit
class TestProjectCreate:
    """Backward-compatible tests — default stack (python)."""

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

    def test_default_stack_is_python(self, executor, sandbox_dir):
        result = executor["project.create"]("default_proj")
        assert result.data["stack"] == "python"

    def test_message_includes_stack_name(self, executor, sandbox_dir):
        result = executor["project.create"]("msg_proj")
        assert "Python" in result.message or "python" in result.message


@pytest.mark.unit
class TestProjectCreateExplicitStack:
    """Explicit --stack flag via the stack parameter."""

    def test_python_stack_creates_main_py(self, executor, sandbox_dir):
        executor["project.create"]("py_proj", stack="python")
        assert (sandbox_dir / "py_proj" / "src" / "main.py").exists()

    def test_python_stack_data_contains_stack(self, executor, sandbox_dir):
        result = executor["project.create"]("py_data", stack="python")
        assert result.data["stack"] == "python"

    def test_node_stack_creates_package_json(self, executor, sandbox_dir):
        result = executor["project.create"]("node_proj", stack="node")
        assert (sandbox_dir / "node_proj" / "package.json").exists()
        assert result.data["stack"] == "node"

    def test_node_stack_creates_index_js(self, executor, sandbox_dir):
        executor["project.create"]("node_idx", stack="node")
        assert (sandbox_dir / "node_idx" / "src" / "index.js").exists()

    def test_node_message_includes_stack(self, executor, sandbox_dir):
        result = executor["project.create"]("node_msg", stack="node")
        assert "Node" in result.message or "node" in result.message

    def test_react_stack_creates_app_jsx(self, executor, sandbox_dir):
        result = executor["project.create"]("react_proj", stack="react")
        assert (sandbox_dir / "react_proj" / "src" / "App.jsx").exists()
        assert result.data["stack"] == "react"

    def test_react_stack_has_package_json(self, executor, sandbox_dir):
        executor["project.create"]("react_pkg", stack="react")
        pkg = sandbox_dir / "react_pkg" / "package.json"
        assert pkg.exists()
        content = pkg.read_text(encoding="utf-8")
        assert "react" in content

    def test_react_stack_has_public_index(self, executor, sandbox_dir):
        executor["project.create"]("react_pub", stack="react")
        assert (sandbox_dir / "react_pub" / "public" / "index.html").exists()

    def test_fastapi_stack_creates_main_py(self, executor, sandbox_dir):
        result = executor["project.create"]("api_proj", stack="fastapi")
        assert result.data["stack"] == "fastapi"
        module = sandbox_dir / "api_proj" / "api_proj"
        assert (module / "main.py").exists()

    def test_fastapi_stack_has_requirements(self, executor, sandbox_dir):
        executor["project.create"]("api_req", stack="fastapi")
        req = sandbox_dir / "api_req" / "requirements.txt"
        assert req.exists()
        content = req.read_text(encoding="utf-8")
        assert "fastapi" in content

    def test_fastapi_stack_has_test_file(self, executor, sandbox_dir):
        executor["project.create"]("api_test", stack="fastapi")
        assert (sandbox_dir / "api_test" / "tests" / "test_root.py").exists()


@pytest.mark.unit
class TestProjectCreateErrors:
    """Error paths: unknown stack, empty path, non-empty directory."""

    def test_unknown_stack_raises(self, executor, sandbox_dir):
        with pytest.raises(ExecutionError, match="Unknown stack"):
            executor["project.create"]("bad_proj", stack="golang")

    def test_empty_path_raises(self, executor, sandbox_dir):
        with pytest.raises(ExecutionError, match="[Pp]ath is required"):
            executor["project.create"]("")

    def test_whitespace_path_raises(self, executor, sandbox_dir):
        with pytest.raises(ExecutionError, match="[Pp]ath is required"):
            executor["project.create"]("   ")

    def test_existing_nonempty_dir_fails(self, executor, sandbox_dir):
        target = sandbox_dir / "occupied"
        target.mkdir()
        (target / "file.txt").touch()
        result = executor["project.create"]("occupied", stack="node")
        assert result.success is False

    def test_result_data_contains_files_list(self, executor, sandbox_dir):
        result = executor["project.create"]("files_proj", stack="python")
        assert isinstance(result.data["files"], list)
        assert len(result.data["files"]) > 0
