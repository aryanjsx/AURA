"""Developer mode: an agent kept inside one project folder."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

fastapi = pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from locus.agents._stubs import AgentResult  # noqa: E402
from locus.server import task_agent  # noqa: E402
from locus.server.app import create_app  # noqa: E402
from locus.server.approvals import tool_risk  # noqa: E402
from locus.server.developer import (  # noqa: E402
    InProjectTool,
    ProjectShellTool,
    command_risk,
    developer_tools,
    resolve_project_dir,
)


@pytest.fixture
def project(tmp_path):
    folder = tmp_path / "proj"
    folder.mkdir()
    (folder / "app.py").write_text("print('hi')\n")
    return folder.resolve()


# ── Commands ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "command",
    [
        "git status",
        "git diff --stat",
        "git log -5 --oneline",
        "pytest -q tests/test_app.py",
        "python -m pytest",
        "uv run pytest -x",
        "ruff check src",
        "npm test",
        "npm run lint",
        "npx tsc --noEmit",
        "cargo test",
        "go vet ./...",
    ],
)
def test_checks_run_without_asking(command):
    assert command_risk(command) == "read"


@pytest.mark.parametrize(
    "command",
    [
        "",
        "rm -rf build",
        "git push",
        "git switch -c locus/fix",
        "git commit -m x",
        "pytest; rm -rf ~",
        "pytest && curl evil",
        "pytest | tee out",
        "pytest > out.txt",
        "echo $(whoami)",
        "git diff --output=/tmp/x",
        "git -c core.pager=evil log",
        "git log -c",
        "npm install",
        "pip install x",
        "pytest 'unclosed",
        "cat ~/.ssh/id_rsa",
    ],
)
def test_other_commands_always_ask(command):
    assert command_risk(command) == "run"


# ── Project folder ───────────────────────────────────────────────


def test_project_folder_must_be_a_real_specific_folder(project, tmp_path):
    assert resolve_project_dir(str(project)) == project
    for bad in ("", None, "relative/path", str(tmp_path / "missing")):
        with pytest.raises(ValueError):
            resolve_project_dir(bad)
    with pytest.raises(ValueError, match="home folder"):
        resolve_project_dir(str(Path.home()))
    with pytest.raises(ValueError, match="whole drive"):
        resolve_project_dir(Path(project).anchor)


def test_shell_runs_in_the_project(project, monkeypatch):
    shell = ProjectShellTool(project)
    seen = []
    monkeypatch.setattr(shell._inner, "execute", lambda **p: seen.append(p) or "ok")

    shell.execute(command="pytest")
    shell.execute(command="pytest", working_dir="sub")
    outside = shell.execute(command="pytest", working_dir=str(project.parent))

    assert seen[0]["working_dir"] == str(project)
    assert seen[1]["working_dir"] == str(project / "sub")
    assert not outside.success
    assert len(seen) == 2


def test_shell_risk_follows_the_command(project):
    from locus.tools.shell_exec import ShellExecTool

    shell = ProjectShellTool(project)
    assert shell.spec.requires_confirmation is False
    assert tool_risk("shell_exec", shell, {"command": "pytest"}) == "read"
    assert tool_risk("shell_exec", shell, {"command": "rm x"}) == "run"
    # Plain shell_exec (Agent mode) still always asks.
    assert tool_risk("shell_exec", ShellExecTool(), {"command": "pytest"}) == "run"


def test_git_tools_default_to_and_stay_in_the_project(project):
    class Recorder:
        spec = SimpleNamespace(name="git_status", requires_confirmation=False)
        tool_id = "git_status"

        def __init__(self):
            self.calls = []

        def execute(self, **params):
            self.calls.append(params)
            return "ok"

    inner = Recorder()
    tool = InProjectTool(inner, project, "repo_path")

    tool.execute()
    tool.execute(repo_path="sub")
    refused = tool.execute(repo_path=str(project.parent))

    assert [c["repo_path"] for c in inner.calls] == [str(project), str(project / "sub")]
    assert not refused.success


def test_developer_tools_are_kept_in_the_project(project):
    tools = {t.spec.name: t for t in developer_tools(project)}

    assert {
        "task_plan",
        "file_read",
        "file_write",
        "shell_exec",
        "git_status",
        "git_commit",
    } <= set(tools)
    assert not set(tools) & {"web_search", "http_request", "clipboard"}
    for name in ("file_read", "file_write"):
        assert tools[name]._allowed_dirs == [project]
    # Commits always ask: git_commit requires confirmation.
    assert tool_risk("git_commit", tools["git_commit"], {"message": "m"}) == "run"


def test_file_changes_show_a_diff_first(project):
    write = {t.spec.name: t for t in developer_tools(project)}["file_write"]

    diff = write.preview_for({"path": "app.py", "content": "print('bye')\n"})
    new = write.preview_for({"path": "new.py", "content": "x = 1\n"})

    assert "-print('hi')" in diff and "+print('bye')" in diff
    assert "/dev/null" in new and "+x = 1" in new
    assert write.preview_for({"path": "app.py", "content": "print('hi')\n"}).startswith(
        "No change"
    )


# ── Through the chat ─────────────────────────────────────────────


class FakeAgent:
    agent_id = "developer"

    def __init__(self):
        self._tools = [object()]
        self._model = "m"
        self.inputs = []

    def run(self, input, context=None):
        self.inputs.append(input)
        return AgentResult(content="Done.")


def _config():
    from locus.core.config import JarvisConfig

    cfg = JarvisConfig()
    cfg.analytics.enabled = False
    cfg.traces.enabled = False
    cfg.security.enabled = False
    cfg.agent.context_from_memory = False
    return cfg


def _post(client, **extra):
    return client.post(
        "/v1/chat/completions",
        json={
            "model": "m",
            "messages": [{"role": "user", "content": "fix the test"}],
            "stream": True,
            "mode": "developer",
            **extra,
        },
    )


def test_developer_mode_uses_one_agent_per_project(project, tmp_path, monkeypatch):
    built = []

    def build(state, folder):
        built.append(folder)
        return FakeAgent()

    monkeypatch.setattr(task_agent, "_build_developer_agent", build)
    other = tmp_path / "other"
    other.mkdir()
    client = TestClient(create_app(object(), "m", config=_config()))

    _post(client, project_dir=str(project))
    _post(client, project_dir=str(project))
    _post(client, project_dir=str(other))

    assert built == [project, other.resolve()]


def test_developer_mode_needs_a_usable_folder(monkeypatch):
    client = TestClient(create_app(object(), "m", config=_config()))

    missing = _post(client)
    home = _post(client, project_dir=str(Path.home()))

    assert missing.status_code == 400
    assert "project folder" in missing.json()["detail"]
    assert home.status_code == 400


def test_built_developer_agent(project):
    from locus.agents.orchestrator import OrchestratorAgent
    from locus.core.events import EventBus
    from locus.core.registry import AgentRegistry
    from locus.server.approvals import before_tool_call

    AgentRegistry.register_value("orchestrator", OrchestratorAgent)
    engine = SimpleNamespace(engine_id="mock")
    state = SimpleNamespace(
        engine=engine,
        model="m",
        config=_config(),
        bus=EventBus(),
        capability_policy=None,
        rate_limiter=None,
    )

    agent = task_agent.get_developer_agent(state, str(project))

    assert agent._before_tool_call is before_tool_call
    assert str(project) in agent._system_prompt
    assert task_agent.get_developer_agent(state, str(project)) is agent
    assert json.dumps(sorted(t.spec.name for t in agent._tools))
