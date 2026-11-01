"""Attachments, images and web search on /v1/chat/completions."""

from __future__ import annotations

import datetime as dt
import json
from unittest.mock import MagicMock

import pytest

fastapi = pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from locus.core.types import Role  # noqa: E402
from locus.server import routes  # noqa: E402
from locus.server.app import create_app  # noqa: E402
from locus.server.web_context import (  # noqa: E402
    WebSearchResult,
    WebSource,
    parse_results,
    render_context,
)


def _recording_engine(seen: list):
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


@pytest.fixture
def seen():
    return []


@pytest.fixture
def client(seen, monkeypatch):
    routes._vision_cache.clear()
    agent = MagicMock()
    agent._tools = [object()]
    app = create_app(
        _recording_engine(seen), "test-model", agent=agent, config=_config()
    )
    return TestClient(app)


def _post(client, messages, **extra):
    return client.post(
        "/v1/chat/completions",
        json={"model": "test-model", "messages": messages, "stream": True, **extra},
    )


def _events(resp):
    """``(event_name, data)`` pairs from an SSE body."""
    out, name = [], None
    for line in resp.text.split("\n"):
        if line.startswith("event: "):
            name = line[7:].strip()
        elif line.startswith("data: "):
            out.append((name, line[6:]))
            name = None
    return out


class TestAttachments:
    def test_documents_are_folded_into_the_message(self, client, seen):
        resp = _post(
            client,
            [
                {
                    "role": "user",
                    "content": "Summarize this",
                    "attachments": [
                        {"name": "notes.txt", "format": "text", "text": "Buy milk"}
                    ],
                }
            ],
        )
        assert resp.status_code == 200
        user = [m for m in seen[0] if m.role == Role.USER][-1]
        assert (
            '<attached_file name="notes.txt" format="text">\nBuy milk' in user.content
        )
        assert user.content.endswith("Summarize this")

    def test_extras_bypass_the_server_agent(self, client, seen):
        # The agent only sees the latest message's text, so the request must
        # reach the engine directly for the attachment to be used.
        _post(
            client,
            [
                {
                    "role": "user",
                    "content": "x",
                    "attachments": [{"name": "a", "text": "b"}],
                }
            ],
        )
        assert len(seen) == 1

    def test_images_reach_a_vision_model(self, client, seen, monkeypatch):
        async def yes(engine, model):
            return True

        monkeypatch.setattr(routes, "_model_accepts_images", yes)
        _post(
            client,
            [{"role": "user", "content": "What is this?", "images": ["aGVsbG8="]}],
        )
        user = [m for m in seen[0] if m.role == Role.USER][-1]
        assert user.images == ["aGVsbG8="]

    def test_images_become_a_note_for_text_only_models(self, client, seen, monkeypatch):
        async def no(engine, model):
            return False

        monkeypatch.setattr(routes, "_model_accepts_images", no)
        _post(
            client, [{"role": "user", "content": "What is this?", "images": ["a", "b"]}]
        )
        user = [m for m in seen[0] if m.role == Role.USER][-1]
        assert user.images is None
        assert "attached 2 image(s)" in user.content
        assert "vision model" in user.content


class TestWebSearch:
    @pytest.fixture
    def search(self, monkeypatch):
        calls = []

        async def fake_search(query):
            calls.append(query)
            return WebSearchResult(
                query=query,
                engine="duckduckgo",
                sources=[
                    WebSource(
                        ref=1,
                        title="Ollama",
                        url="https://ollama.com",
                        text="Run models locally.",
                    )
                ],
            )

        monkeypatch.setattr("locus.server.web_context.search_web", fake_search)
        return calls

    def test_sources_arrive_before_the_answer(self, client, search):
        resp = _post(
            client, [{"role": "user", "content": "What is Ollama?"}], web_search=True
        )
        events = _events(resp)
        assert events[0][0] == "web_search"
        payload = json.loads(events[0][1])
        assert payload["query"] == "What is Ollama?"
        assert payload["sources"] == [
            {"ref": 1, "title": "Ollama", "url": "https://ollama.com"}
        ]
        assert events[-1][1] == "[DONE]"

    def test_results_are_in_the_system_prompt_with_identity(self, client, seen, search):
        _post(client, [{"role": "user", "content": "What is Ollama?"}], web_search=True)
        system = [m for m in seen[0] if m.role == Role.SYSTEM]
        assert len(system) == 1
        assert (
            "[1] Ollama\nURL: https://ollama.com\nRun models locally."
            in system[0].content
        )
        # The search results don't count as a caller system prompt, so the
        # server's identity prompt is still there ahead of them.
        assert system[0].content.index("[1] Ollama") > 0
        assert system[0].name is None

    def test_searches_the_latest_user_message(self, client, search):
        _post(
            client,
            [
                {"role": "user", "content": "first"},
                {"role": "assistant", "content": "ok"},
                {"role": "user", "content": "weather in Pune today"},
            ],
            web_search=True,
        )
        assert search == ["weather in Pune today"]

    def test_off_by_default(self, client, search):
        resp = _post(client, [{"role": "user", "content": "hello"}])
        assert search == []
        assert all(name != "web_search" for name, _ in _events(resp))


class TestWebContext:
    def test_parse_results(self):
        content = (
            "### First\nSource: https://a.example\nSummary: Alpha\n\n---\n\n"
            "### Second\nSource: https://b.example\nSummary: Beta\nmore"
        )
        sources = parse_results(content)
        assert [(s.ref, s.title, s.url, s.snippet) for s in sources] == [
            (1, "First", "https://a.example", "Alpha"),
            (2, "Second", "https://b.example", "Beta\nmore"),
        ]

    def test_render_prefers_page_text_and_dates_results(self):
        result = WebSearchResult(
            query="q",
            sources=[
                WebSource(
                    ref=1,
                    title="T",
                    url="https://t.example",
                    snippet="short",
                    text="full page",
                )
            ],
        )
        context = render_context(result, today=dt.date(2026, 11, 1))
        assert "retrieved 2026-11-01" in context
        assert "full page" in context and "short" not in context
        assert "[1], [2]" in context

    def test_render_failure_tells_the_model(self):
        context = render_context(
            WebSearchResult(query="q", error="The web search timed out.")
        )
        assert "timed out" in context
        assert "couldn't check the web" in context
