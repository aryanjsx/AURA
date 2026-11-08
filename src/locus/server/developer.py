"""Developer mode: an Agent mode agent working inside one project folder.

File, git and shell tools are kept in the project. Tests, linters and
read-only git commands run without asking; any other command asks every time.
"""

from __future__ import annotations

import dataclasses
import shlex
from pathlib import Path
from typing import Any, Optional

from locus.core.types import ToolResult
from locus.tools._stubs import BaseTool, ToolSpec

#: Commands that only check the project. A command runs without asking only
#: when it starts with one of these and has no shell operators.
SAFE_COMMANDS: tuple[tuple[str, ...], ...] = (
    ("git", "status"),
    ("git", "diff"),
    ("git", "log"),
    ("git", "show"),
    ("pytest",),
    ("python", "-m", "pytest"),
    ("uv", "run", "pytest"),
    ("ruff", "check"),
    ("ruff", "format", "--check"),
    ("uv", "run", "ruff", "check"),
    ("uv", "run", "ruff", "format", "--check"),
    ("npm", "test"),
    ("npm", "run", "test"),
    ("npm", "run", "lint"),
    ("npx", "vitest", "run"),
    ("npx", "tsc", "--noEmit"),
    ("npx", "eslint"),
    ("cargo", "test"),
    ("cargo", "check"),
    ("cargo", "clippy"),
    ("go", "test"),
    ("go", "vet"),
)

# Anything that chains, redirects, substitutes or expands needs a person.
_SHELL_OPERATORS = set(";&|<>`$(){}^%!\n\r")
# Flags that make an otherwise read-only command write or run something.
_UNSAFE_FLAGS = ("--output", "--ext-diff", "--exec", "-c", "--config")


def command_risk(command: str) -> str:
    """``"read"`` for a known check (tests, linters, git status); else ``"run"``."""
    if not command or any(ch in _SHELL_OPERATORS for ch in command):
        return "run"
    try:
        tokens = shlex.split(command)
    except ValueError:
        return "run"
    for prefix in SAFE_COMMANDS:
        if tuple(tokens[: len(prefix)]) == prefix:
            rest = tokens[len(prefix) :]
            if any(
                t == f or t.startswith(f + "=") for t in rest for f in _UNSAFE_FLAGS
            ):
                return "run"
            return "read"
    return "run"


def resolve_project_dir(raw: Optional[str]) -> Path:
    """The project folder, or ``ValueError`` saying why it can't be used."""
    if not raw or not str(raw).strip():
        raise ValueError("Choose a project folder for developer mode.")
    path = Path(str(raw).strip()).expanduser()
    if not path.is_absolute():
        raise ValueError("The project folder must be a full path.")
    path = path.resolve()
    if not path.is_dir():
        raise ValueError(f"{path} isn't a folder.")
    if path == Path(path.anchor) or path == Path.home().resolve():
        raise ValueError(
            "Choose a project folder, not a whole drive or your home folder."
        )
    return path


def _inside(path: Path, project: Path) -> bool:
    resolved = path.resolve()
    return resolved == project or resolved.is_relative_to(project)


class InProjectTool(BaseTool):
    """Wraps a tool that takes ``path_param`` so it stays in the project."""

    def __init__(self, inner: BaseTool, project: Path, path_param: str) -> None:
        self._inner = inner
        self._project = project
        self._path_param = path_param
        self.tool_id = getattr(inner, "tool_id", inner.spec.name)

    @property
    def spec(self) -> ToolSpec:
        return self._inner.spec

    def __getattr__(self, name: str) -> Any:
        # risk_for, preview_for and anything else the inner tool offers.
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._inner, name)

    def execute(self, **params: Any) -> ToolResult:
        raw = params.get(self._path_param) or str(self._project)
        path = Path(str(raw))
        if not path.is_absolute():
            path = self._project / path
        if not _inside(path, self._project):
            return ToolResult(
                tool_name=self.spec.name,
                content=f"{raw} is outside the project folder {self._project}.",
                success=False,
            )
        return self._inner.execute(**{**params, self._path_param: str(path)})


class ProjectShellTool(BaseTool):
    """``shell_exec`` in the project folder, with read-only checks pre-approved.

    It isn't marked ``requires_confirmation``: approvals ask by its own
    :meth:`risk_for` instead, which is ``run`` for anything but known checks.
    """

    def __init__(self, project: Path) -> None:
        from locus.tools.shell_exec import ShellExecTool

        self._inner = ShellExecTool()
        self._project = project
        self.tool_id = "shell_exec"

    @property
    def spec(self) -> ToolSpec:
        spec = self._inner.spec
        return dataclasses.replace(
            spec,
            description=(
                f"{spec.description} Commands run in the project folder"
                f" ({self._project}) unless working_dir names a folder inside"
                " it. Tests, linters and git status/diff/log run right away;"
                " other commands need the user's approval."
            ),
            requires_confirmation=False,
        )

    def risk_for(self, arguments: dict) -> str:
        return command_risk(str(arguments.get("command") or ""))

    def execute(self, **params: Any) -> ToolResult:
        working_dir = Path(str(params.get("working_dir") or self._project))
        if not working_dir.is_absolute():
            working_dir = self._project / working_dir
        if not _inside(working_dir, self._project):
            return ToolResult(
                tool_name="shell_exec",
                content=f"{working_dir} is outside the project folder.",
                success=False,
            )
        return self._inner.execute(**{**params, "working_dir": str(working_dir)})


_DEVELOPER_RULES = (
    "For anything with more than one step, show your plan with task_plan first"
    " and update it as you go.",
    "Read the relevant code with file_read before changing it. Change files"
    " with file_write, giving the whole new file; the user reviews a diff"
    " before it's written.",
    "Before your first change, run `git status`. If the project is a git"
    " repository on main or master, create a branch with"
    " `git switch -c locus/<short-topic>` (the user approves it).",
    "After changing code, run the project's tests or checks (for example"
    " pytest, npm test or cargo test). If they fail, read the failure, fix it"
    " and run them again, up to 3 times, then report what's left.",
    "Never push, delete branches or delete files unless the user asks. Commit"
    " only when the user asks, with a short message saying what changed and"
    " why.",
    "Keep replies short: what you changed, and the test result.",
)


def developer_prompt(project: Path) -> str:
    rules = "\n".join(f"- {rule}" for rule in _DEVELOPER_RULES)
    return (
        f"You are Locus in developer mode, working on the project in {project}."
        f"\n\nHow to work:\n{rules}"
    )


def developer_tools(project: Path, config: Any = None) -> list:
    """The developer agent's tools, all kept inside *project*."""
    from locus.tools.calculator import CalculatorTool
    from locus.tools.file_read import FileReadTool
    from locus.tools.git_tool import (
        GitCommitTool,
        GitDiffTool,
        GitLogTool,
        GitStatusTool,
    )
    from locus.tools.task_plan import TaskPlanTool
    from locus.tools.think import ThinkTool
    from locus.tools.undo_journal import UndoableFileWriteTool

    folder = [str(project)]
    tools: list = [
        TaskPlanTool(),
        ThinkTool(),
        CalculatorTool(),
        FileReadTool(allowed_dirs=folder),
        UndoableFileWriteTool(allowed_dirs=folder),
        ProjectShellTool(project),
    ]
    for git_tool in (GitStatusTool(), GitDiffTool(), GitLogTool(), GitCommitTool()):
        tools.append(InProjectTool(git_tool, project, "repo_path"))
    return tools


__all__ = [
    "SAFE_COMMANDS",
    "InProjectTool",
    "ProjectShellTool",
    "command_risk",
    "developer_prompt",
    "developer_tools",
    "resolve_project_dir",
]
