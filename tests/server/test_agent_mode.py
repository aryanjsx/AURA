"""Agent mode (``mode`` on /v1/chat/completions) and live agent events."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

fastapi = pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from locus.agents._stubs import AgentResult  # noqa: E402
from locus.core.events import EventBus, EventType  # noqa: E402
from locus.server import task_agent  # noqa: E402
from locus.server.app import create_app  # noqa: E402


def _engine(seen: list):
    engine = MagicMock()
    engine.engine_id = "mock"
    engine.health.return_value = True
    engine.list_models.return_value = ["test-model"]

    async def stream(messages, *, model, temperature=0.7, max_tokens=1024, **kwargs):
        seen.append(list(messages))
        for token in ["Hi", "!"]:
            yield token

    engine.stream = stream
    return engine


def _config():
    from locus.core.config import JarvisConfig

    cfg = JarvisConfig()
    cfg.analytics.enabled = False
    cfg.traces.enabled = False
    cfg.security.enabled = False
    cfg.agent.context_from_memory = False
    return cfg


class FakeAgent:
    """A tool agent that publishes its own events and one from another agent."""

    agent_id = "fake"

    def __init__(self, bus=None, tools=True):
        self._bus = bus
        self._tools = [object()] if tools else []
        self._model = "test-model"
        self.inputs: list[str] = []
        self.contexts: list = []

    def run(self, input, context=None):
        self.inputs.append(input)
        self.contexts.append(context)
        if self._bus is not None:
            self._bus.publish(
                EventType.TOOL_CALL_START,
                {"tool": "file_read", "arguments": {"path": "a.txt"}, "agent": "fake"},
            )
            self._bus.publish(
                EventType.TOOL_CALL_START,
                {"tool": "shell_exec", "arguments": {}, "agent": "someone-else"},
            )
            self._bus.publish(
                EventType.TOOL_CALL_END,
                {
                    "tool": "file_read",
                    "success": True,
                    "latency": 0.01,
                    "result": "hello",
                    "agent": "fake",
                },
            )
        return AgentResult(content="Done.")


def _post(client, **extra):
    body = {
        "model": "test-model",
        "messages": [{"role": "user", "content": "read a.txt"}],
        "stream": True,
        **extra,
    }
    return client.post("/v1/chat/completions", json=body)


def _events(resp):
    out, name = [], None
    for line in resp.text.split("\n"):
        if line.startswith("event: "):
            name = line[7:].strip()
        elif line.startswith("data: "):
            if name:
                out.append((name, json.loads(line[6:])))
            name = None
    return out


def _content(resp):
    text = ""
    for line in resp.text.split("\n"):
        if line.startswith("data: ") and line[6:] != "[DONE]":
            data = json.loads(line[6:])
            for choice in data.get("choices", []):
                text += choice.get("delta", {}).get("content") or ""
    return text


def test_chat_mode_skips_the_configured_tool_agent():
    seen: list = []
    agent = FakeAgent()
    app = create_app(_engine(seen), "test-model", agent=agent, config=_config())

    resp = _post(TestClient(app), mode="chat")

    assert resp.status_code == 200
    assert agent.inputs == []
    assert seen, "chat mode should stream from the engine"
    assert _content(resp) == "Hi!"


def test_agent_mode_uses_its_own_agent_even_when_the_configured_one_has_tools(
    monkeypatch,
):
    # Only the Agent mode agent asks before tools that change something.
    bus = EventBus()
    configured = FakeAgent(bus=bus)
    built = FakeAgent(bus=bus)
    monkeypatch.setattr(task_agent, "_build_task_agent", lambda state: built)
    app = create_app(
        _engine([]), "test-model", agent=configured, bus=bus, config=_config()
    )

    resp = _post(TestClient(app), mode="agent")

    assert configured.inputs == []
    assert built.inputs == ["read a.txt"]
    assert _content(resp) == "Done."


def test_agent_mode_builds_an_agent_when_the_configured_one_has_none(monkeypatch):
    seen: list = []
    bus = EventBus()
    built = FakeAgent(bus=bus)
    monkeypatch.setattr(task_agent, "_build_task_agent", lambda state: built)
    simple = FakeAgent(tools=False)
    app = create_app(
        _engine(seen), "test-model", agent=simple, bus=bus, config=_config()
    )
    client = TestClient(app)

    _post(client, mode="agent")
    _post(client, mode="agent")

    assert built.inputs == ["read a.txt", "read a.txt"]
    assert simple.inputs == []
    assert app.state.task_agent is built
    # Without a mode the request still goes where it did before.
    _post(client)
    assert seen


def test_agent_mode_streams_only_its_own_tool_events(monkeypatch):
    bus = EventBus()
    agent = FakeAgent(bus=bus)
    monkeypatch.setattr(task_agent, "_build_task_agent", lambda state: agent)
    app = create_app(_engine([]), "test-model", bus=bus, config=_config())

    events = _events(_post(TestClient(app), mode="agent"))

    starts = [data for name, data in events if name == "tool_call_start"]
    ends = [data for name, data in events if name == "tool_call_end"]
    assert [s["tool"] for s in starts] == ["file_read"]
    assert json.loads(starts[0]["arguments"]) == {"path": "a.txt"}
    assert [(e["tool"], e["success"], e["result"]) for e in ends] == [
        ("file_read", True, "hello")
    ]


def test_agent_mode_gets_web_results_as_context(monkeypatch):
    from locus.server import web_context

    seen: list = []
    agent = FakeAgent()
    monkeypatch.setattr(task_agent, "_build_task_agent", lambda state: agent)

    async def results(query):
        return web_context.WebSearchResult(
            query=query,
            sources=[
                web_context.WebSource(
                    ref=1, title="Docs", url="https://example.com", text="Answer 42"
                )
            ],
        )

    monkeypatch.setattr(web_context, "search_web", results)
    app = create_app(_engine(seen), "test-model", config=_config())

    resp = _post(TestClient(app), mode="agent", web_search=True)

    assert agent.inputs == ["read a.txt"]
    assert seen == []
    system = [
        m for m in agent.contexts[0].conversation.messages if m.role.value == "system"
    ]
    assert any("Answer 42" in m.content for m in system)
    assert any(name == "web_search" for name, _ in _events(resp))


def test_agent_mode_gets_attached_documents_and_images(monkeypatch):
    agent = FakeAgent()
    monkeypatch.setattr(task_agent, "_build_task_agent", lambda state: agent)
    app = create_app(_engine([]), "test-model", config=_config())
    monkeypatch.setattr(
        "locus.server.routes._model_accepts_images",
        lambda engine, model: _true(),
    )

    TestClient(app).post(
        "/v1/chat/completions",
        json={
            "model": "test-model",
            "stream": True,
            "mode": "agent",
            "messages": [
                {
                    "role": "user",
                    "content": "earlier",
                    "attachments": [{"name": "old.txt", "text": "OLD NOTES"}],
                },
                {"role": "assistant", "content": "ok"},
                {
                    "role": "user",
                    "content": "summarize",
                    "attachments": [{"name": "plan.md", "text": "THE PLAN"}],
                    "images": ["aW1n"],
                },
            ],
        },
    )

    assert "THE PLAN" in agent.inputs[0]
    assert agent.inputs[0].endswith("summarize")
    context = agent.contexts[0]
    assert "OLD NOTES" in context.conversation.messages[0].content
    assert context.metadata["input_images"] == ["aW1n"]


async def _true():
    return True


def test_agent_mode_falls_back_to_chat_when_the_agent_cannot_start(monkeypatch):
    seen: list = []

    def broken(state):
        raise RuntimeError("no orchestrator")

    monkeypatch.setattr(task_agent, "_build_task_agent", broken)
    app = create_app(
        _engine(seen), "test-model", agent=FakeAgent(tools=False), config=_config()
    )

    resp = _post(TestClient(app), mode="agent")

    assert resp.status_code == 200
    assert _content(resp) == "Hi!"


def test_built_agent_asks_before_changes_and_stays_in_home(monkeypatch):
    # The shared conftest clears registries between tests.
    from locus.agents.orchestrator import OrchestratorAgent
    from locus.core.registry import AgentRegistry, ToolRegistry
    from locus.tools.calculator import CalculatorTool
    from locus.tools.file_read import FileReadTool
    from locus.tools.file_write import FileWriteTool
    from locus.tools.http_request import HttpRequestTool
    from locus.tools.shell_exec import ShellExecTool
    from locus.tools.think import ThinkTool

    AgentRegistry.register_value("orchestrator", OrchestratorAgent)
    for name, cls in [
        ("think", ThinkTool),
        ("calculator", CalculatorTool),
        ("file_read", FileReadTool),
        ("file_write", FileWriteTool),
        ("shell_exec", ShellExecTool),
        ("http_request", HttpRequestTool),
    ]:
        ToolRegistry.register_value(name, cls)

    engine = MagicMock()
    engine.engine_id = "mock"
    state = SimpleNamespace(
        engine=engine,
        model="test-model",
        config=_config(),
        bus=EventBus(),
        capability_policy=None,
        rate_limiter=None,
    )

    agent = task_agent._build_task_agent(state)

    from locus.server.approvals import before_tool_call

    names = {tool.spec.name for tool in agent._tools}
    assert names <= set(task_agent.ASSISTANT_TOOLS)
    assert {"think", "calculator", "file_read", "file_write", "shell_exec"} <= names
    assert not names & {"web_search", "http_request"}
    for name in ("file_read", "file_write"):
        tool = next(t for t in agent._tools if t.spec.name == name)
        assert tool._allowed_dirs == [Path.home().resolve()]
    assert agent._before_tool_call is before_tool_call
    assert agent._parallel_tools is False
    assert agent._max_turns >= task_agent.MIN_MAX_TURNS
    assert task_agent.ASSISTANT_AGENT_ID in task_agent.agent_event_ids(agent)


def test_agents_send_input_images_with_the_last_message():
    from locus.agents._stubs import AgentContext
    from locus.agents.simple import SimpleAgent

    agent = SimpleAgent(MagicMock(), "test-model")
    ctx = AgentContext()
    ctx.metadata["input_images"] = ["aW1n"]

    with_images = agent._build_messages("what is this?", ctx)
    without = agent._build_messages("hi", AgentContext())

    assert with_images[-1].content == "what is this?"
    assert with_images[-1].images == ["aW1n"]
    assert without[-1].images is None


def test_tool_images_are_shown_only_to_vision_models():
    from locus.agents.orchestrator import OrchestratorAgent
    from locus.core.types import Message, Role, ToolResult

    shot = ToolResult(
        tool_name="screenshot", content="ok", metadata={"images": ["aW1n"]}
    )
    plain = ToolResult(tool_name="file_read", content="text")

    messages: list = []
    OrchestratorAgent._attach_tool_images(messages, [plain, shot], vision=True)
    assert len(messages) == 1
    assert messages[0].role == Role.USER
    assert messages[0].images == ["aW1n"]

    blind: list[Message] = []
    OrchestratorAgent._attach_tool_images(blind, [shot], vision=False)
    OrchestratorAgent._attach_tool_images(blind, [plain], vision=True)
    assert blind == []


@pytest.mark.parametrize("sees", [True, False])
def test_agent_mode_tells_the_agent_whether_the_model_sees_images(monkeypatch, sees):
    agent = FakeAgent()
    monkeypatch.setattr(task_agent, "_build_task_agent", lambda state: agent)

    async def accepts(engine, model):
        return sees

    monkeypatch.setattr("locus.server.routes._model_accepts_images", accepts)
    app = create_app(_engine([]), "test-model", config=_config())

    _post(TestClient(app), mode="agent")

    assert agent.contexts[0].metadata["vision"] is sees
