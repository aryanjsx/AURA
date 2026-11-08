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

    def run(self, input, context=None):
        self.inputs.append(input)
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


def test_agent_mode_reuses_a_configured_tool_agent():
    bus = EventBus()
    agent = FakeAgent(bus=bus)
    app = create_app(_engine([]), "test-model", agent=agent, bus=bus, config=_config())

    resp = _post(TestClient(app), mode="agent")

    assert agent.inputs == ["read a.txt"]
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


def test_agent_mode_streams_only_its_own_tool_events():
    bus = EventBus()
    agent = FakeAgent(bus=bus)
    app = create_app(_engine([]), "test-model", agent=agent, bus=bus, config=_config())

    events = _events(_post(TestClient(app), mode="agent"))

    starts = [data for name, data in events if name == "tool_call_start"]
    ends = [data for name, data in events if name == "tool_call_end"]
    assert [s["tool"] for s in starts] == ["file_read"]
    assert json.loads(starts[0]["arguments"]) == {"path": "a.txt"}
    assert [(e["tool"], e["success"], e["result"]) for e in ends] == [
        ("file_read", True, "hello")
    ]


def test_agent_mode_with_web_search_answers_without_the_agent(monkeypatch):
    from locus.server import web_context

    seen: list = []
    agent = FakeAgent()

    async def no_results(query):
        return web_context.WebSearchResult(query=query, sources=[], error="offline")

    monkeypatch.setattr(web_context, "search_web", no_results)
    app = create_app(_engine(seen), "test-model", agent=agent, config=_config())

    _post(TestClient(app), mode="agent", web_search=True)

    assert agent.inputs == []
    assert seen


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


def test_built_agent_uses_read_only_tools_kept_in_home(monkeypatch):
    # The shared conftest clears registries between tests.
    from locus.agents.orchestrator import OrchestratorAgent
    from locus.core.registry import AgentRegistry, ToolRegistry
    from locus.tools.calculator import CalculatorTool
    from locus.tools.file_read import FileReadTool
    from locus.tools.file_write import FileWriteTool
    from locus.tools.think import ThinkTool

    AgentRegistry.register_value("orchestrator", OrchestratorAgent)
    for name, cls in [
        ("think", ThinkTool),
        ("calculator", CalculatorTool),
        ("file_read", FileReadTool),
        ("file_write", FileWriteTool),
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

    names = {tool.spec.name for tool in agent._tools}
    assert names <= set(task_agent.ASSISTANT_TOOLS)
    assert {"think", "calculator", "file_read"} <= names
    assert not names & {"file_write", "shell_exec", "web_search", "http_request"}
    file_read = next(t for t in agent._tools if t.spec.name == "file_read")
    assert file_read._allowed_dirs == [Path.home().resolve()]
    assert task_agent.ASSISTANT_AGENT_ID in task_agent.agent_event_ids(agent)
