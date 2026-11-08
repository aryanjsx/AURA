"""In-chat approvals for Agent mode (``server/approvals.py``)."""

from __future__ import annotations

import json
import threading
from types import SimpleNamespace

import pytest

fastapi = pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from locus.agents._stubs import AgentResult  # noqa: E402
from locus.server import approvals, task_agent  # noqa: E402
from locus.server.app import create_app  # noqa: E402
from locus.server.approvals import (  # noqa: E402
    AgentCancelled,
    ApprovalSession,
    before_tool_call,
    confirm_after_approval,
    tool_risk,
)


def _config():
    from locus.core.config import JarvisConfig

    cfg = JarvisConfig()
    cfg.analytics.enabled = False
    cfg.traces.enabled = False
    cfg.security.enabled = False
    cfg.agent.context_from_memory = False
    return cfg


class Recorder:
    """An ``emit`` that records events and can answer approvals as they come."""

    def __init__(self, answer=None):
        self.events: list[tuple[str, dict]] = []
        self.answer = answer

    def __call__(self, name, data):
        self.events.append((name, data))
        if name == "approval_required" and self.answer is not None:
            approvals.resolve(data["id"], self.answer)

    def names(self):
        return [name for name, _ in self.events]


# ── Risk levels ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name, risk",
    [
        ("file_read", "read"),
        ("think", "read"),
        ("git_status", "read"),
        ("file_write", "change"),
        ("git_commit", "change"),
        ("some_new_tool", "change"),
        ("shell_exec", "run"),
        ("code_interpreter", "run"),
    ],
)
def test_tool_risk(name, risk):
    assert tool_risk(name) == risk


def test_tools_marked_requires_confirmation_always_run_level():
    tool = SimpleNamespace(spec=SimpleNamespace(requires_confirmation=True))
    assert tool_risk("file_read", tool) == "run"


def test_without_a_session_only_read_tools_run():
    assert before_tool_call("file_read", {}) is True
    assert before_tool_call("file_write", {"path": "a"}) is False
    assert before_tool_call("shell_exec", {"command": "ls"}) is False
    assert confirm_after_approval("Allow shell_exec?") is False


# ── Approval sessions ────────────────────────────────────────────


def test_read_tools_never_ask():
    emit = Recorder()
    assert ApprovalSession(emit).check("file_read", {"path": "a"}) is True
    assert emit.events == []


@pytest.mark.parametrize(
    "answer, allowed", [("approve", True), ("approve_tool", True), ("deny", False)]
)
def test_answer_decides_the_call(answer, allowed):
    emit = Recorder(answer=answer)
    session = ApprovalSession(emit)

    assert session.check("shell_exec", {"command": "ls"}) is allowed

    assert emit.names() == ["approval_required", "approval_resolved"]
    required, resolved = emit.events[0][1], emit.events[1][1]
    assert required["tool"] == "shell_exec"
    assert required["arguments"] == {"command": "ls"}
    assert required["risk"] == "run"
    assert resolved == {
        "id": required["id"],
        "tool": "shell_exec",
        "approved": allowed,
        "timed_out": False,
    }


def test_approve_tool_covers_later_calls_in_the_same_run():
    emit = Recorder(answer="approve_tool")
    session = ApprovalSession(emit)

    assert session.check("file_write", {"path": "a"}) is True
    assert session.check("file_write", {"path": "b"}) is True
    assert emit.names().count("approval_required") == 1
    # Other tools, and other runs, still ask.
    emit.answer = "deny"
    assert session.check("shell_exec", {"command": "ls"}) is False
    assert ApprovalSession(emit).check("file_write", {"path": "c"}) is False


def test_approve_covers_only_that_call():
    emit = Recorder(answer="approve")
    session = ApprovalSession(emit)

    session.check("file_write", {"path": "a"})
    session.check("file_write", {"path": "b"})

    assert emit.names().count("approval_required") == 2


def test_no_answer_in_time_is_a_no():
    emit = Recorder()
    session = ApprovalSession(emit, timeout=0.05)

    assert session.check("file_write", {"path": "a"}) is False
    assert emit.events[-1][1]["timed_out"] is True
    # Nothing is left waiting.
    assert approvals.resolve(emit.events[0][1]["id"], "approve") is False


def test_stopping_while_waiting_ends_the_run():
    emit = Recorder()
    session = ApprovalSession(emit)
    raised = []

    def run():
        try:
            session.check("shell_exec", {"command": "ls"})
        except AgentCancelled:
            raised.append(True)

    worker = threading.Thread(target=run)
    worker.start()
    while not emit.events:
        worker.join(0.01)
    with session:
        assert approvals.stop_run(session.run_id) is True
    worker.join(2)

    assert raised == [True]
    with pytest.raises(AgentCancelled):
        session.check("file_read", {})


def test_unknown_ids_are_not_waiting():
    assert approvals.resolve("nope", "approve") is False
    assert approvals.stop_run("nope") is False


# ── Through the chat stream ──────────────────────────────────────


class AskingAgent:
    """Calls the approval hook the way the orchestrator does before each tool."""

    agent_id = "asking"

    def __init__(self, calls):
        # Streams only go to agents that have tools.
        self._tools = [object()]
        self._model = "test-model"
        self._calls = calls
        self.results: list[bool] = []

    def run(self, input, context=None):
        for name, args in self._calls:
            self.results.append(before_tool_call(name, args))
        return AgentResult(content=f"allowed={self.results}")


def _app(monkeypatch, agent):
    monkeypatch.setattr(task_agent, "_build_task_agent", lambda state: agent)
    engine = SimpleNamespace(engine_id="mock", health=lambda: True)
    return create_app(engine, "test-model", config=_config())


def _stream(client):
    """Run an Agent mode stream; return its event names and answer text."""
    body = {
        "model": "test-model",
        "messages": [{"role": "user", "content": "do it"}],
        "stream": True,
        "mode": "agent",
    }
    resp = client.post("/v1/chat/completions", json=body)
    names, content, name = [], "", None
    for line in resp.text.split("\n"):
        if line.startswith("event: "):
            name = line[7:].strip()
        elif line.startswith("data: ") and line[6:] != "[DONE]":
            data = json.loads(line[6:])
            if name:
                names.append(name)
            else:
                for choice in data.get("choices", []):
                    content += choice.get("delta", {}).get("content") or ""
            name = None
    return names, content


def _when_waiting(action):
    """Call ``action(approval_id, run_id)`` once an approval is waiting.

    The test client buffers the whole response, so answers come from another
    thread, the way the UI answers while the stream is open.
    """
    import time

    def watch():
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with approvals._pending_lock:
                pending = next(iter(approvals._pending), None)
                run_id = next(iter(approvals._sessions), None)
            if pending and run_id:
                action(pending, run_id)
                return
            time.sleep(0.01)

    thread = threading.Thread(target=watch, daemon=True)
    thread.start()
    return thread


@pytest.mark.parametrize("decision, allowed", [("approve", True), ("deny", False)])
def test_stream_asks_and_waits_for_the_answer(monkeypatch, decision, allowed):
    agent = AskingAgent([("file_read", {}), ("file_write", {"path": "a.txt"})])
    client = TestClient(_app(monkeypatch, agent))
    answers = []
    watcher = _when_waiting(
        lambda approval_id, _run: answers.append(
            client.post(
                f"/v1/chat/approvals/{approval_id}", json={"decision": decision}
            ).status_code
        )
    )

    names, content = _stream(client)
    watcher.join(5)

    assert answers == [200]
    assert names[0] == "agent_run"
    assert names.count("approval_required") == 1
    assert "approval_resolved" in names
    assert agent.results == [True, allowed]
    assert content == f"allowed={[True, allowed]}"


def test_stop_ends_the_run(monkeypatch):
    agent = AskingAgent([("shell_exec", {"command": "ls"}), ("file_read", {})])
    client = TestClient(_app(monkeypatch, agent))
    stops = []
    watcher = _when_waiting(
        lambda _approval, run_id: stops.append(
            (run_id, client.post(f"/v1/chat/runs/{run_id}/stop").status_code)
        )
    )

    _, content = _stream(client)
    watcher.join(5)

    assert [code for _, code in stops] == [200]
    assert content == "Stopped."
    assert agent.results == []
    assert client.post(f"/v1/chat/runs/{stops[0][0]}/stop").status_code == 404


def test_answering_a_finished_approval_is_404(monkeypatch):
    client = TestClient(_app(monkeypatch, AskingAgent([])))
    resp = client.post("/v1/chat/approvals/gone", json={"decision": "approve"})
    assert resp.status_code == 404
    resp = client.post("/v1/chat/approvals/gone", json={"decision": "maybe"})
    assert resp.status_code == 422


def test_non_streaming_agent_mode_denies_changes(monkeypatch):
    agent = AskingAgent([("file_read", {}), ("file_write", {"path": "a.txt"})])
    client = TestClient(_app(monkeypatch, agent))

    resp = client.post(
        "/v1/chat/completions",
        json={
            "model": "test-model",
            "messages": [{"role": "user", "content": "do it"}],
            "mode": "agent",
        },
    )

    assert resp.status_code == 200
    assert agent.results == [True, False]


# ── Lasting rules ────────────────────────────────────────────────


def test_rule_keys_cover_one_action():
    from locus.server.approvals import rule_key

    assert rule_key("file_write", {"path": "a"}) == "file_write"
    assert (
        rule_key("system_control", {"action": "set_volume"})
        == "system_control:set_volume"
    )


def test_always_saves_a_rule_that_later_runs_use():
    emit = Recorder(answer="always")
    assert ApprovalSession(emit).check("system_control", {"action": "set_volume"})

    later = Recorder(answer="deny")
    session = ApprovalSession(later)
    # The same action no longer asks, in a new run.
    assert session.check("system_control", {"action": "set_volume", "level": 10})
    assert later.events == []
    # Other actions of the tool still ask.
    assert session.check("system_control", {"action": "lock_screen"}) is False
    assert later.names().count("approval_required") == 1
    required = emit.events[0][1]
    assert required["can_always"] is True
    assert required["rule"] == "system_control:set_volume"


def test_run_level_calls_never_get_lasting_rules():
    emit = Recorder(answer="always")
    assert ApprovalSession(emit).check("shell_exec", {"command": "ls"})
    assert emit.events[0][1]["can_always"] is False

    later = Recorder(answer="deny")
    assert ApprovalSession(later).check("shell_exec", {"command": "ls"}) is False
    assert approvals.get_rules().list() == []


def test_rules_can_be_listed_and_removed(monkeypatch):
    client = TestClient(_app(monkeypatch, AskingAgent([])))
    approvals.get_rules().add("file_write", {"path": "a"})

    rules = client.get("/v1/chat/permissions").json()["rules"]
    assert [r["key"] for r in rules] == ["file_write"]
    assert client.delete("/v1/chat/permissions/file_write").status_code == 200
    assert client.get("/v1/chat/permissions").json()["rules"] == []
    assert client.delete("/v1/chat/permissions/file_write").status_code == 404


def test_rules_survive_a_restart(tmp_path):
    from locus.server.approvals import PermissionRules

    path = tmp_path / "rules.json"
    PermissionRules(path).add("clipboard", {"action": "write"})
    assert PermissionRules(path).allows("clipboard", {"action": "write"})
    assert not PermissionRules(path).allows("clipboard", {"action": "read"})


def test_previews_come_from_the_tool():
    class Previewing:
        def preview_for(self, arguments):
            return "x" * (approvals.MAX_PREVIEW_CHARS + 10)

    emit = Recorder(answer="deny")
    ApprovalSession(emit, tools={"file_write": Previewing()}).check("file_write", {})

    preview = emit.events[0][1]["preview"]
    assert preview.startswith("x" * approvals.MAX_PREVIEW_CHARS)
    assert preview.endswith("(preview cut off)")
