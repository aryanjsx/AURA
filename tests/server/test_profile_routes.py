"""The user's name in USER.md, and the assistant using their nickname."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

fastapi = pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from locus.core.types import Role  # noqa: E402
from locus.server.app import create_app  # noqa: E402
from locus.server.profile_routes import (  # noqa: E402
    END,
    START,
    Profile,
    parse_block,
    render_block,
)


def _config(user_path):
    from locus.core.config import JarvisConfig

    cfg = JarvisConfig()
    cfg.analytics.enabled = False
    cfg.traces.enabled = False
    cfg.security.enabled = False
    cfg.agent.context_from_memory = False
    cfg.memory_files.user_path = str(user_path)
    cfg.memory_files.soul_path = ""
    cfg.memory_files.memory_path = ""
    return cfg


@pytest.fixture
def user_md(tmp_path):
    return tmp_path / "USER.md"


@pytest.fixture
def seen():
    return []


@pytest.fixture
def client(user_md, seen):
    engine = MagicMock()
    engine.engine_id = "mock"
    engine.health.return_value = True
    engine.list_models.return_value = ["test-model"]

    async def stream(messages, *, model, temperature=0.7, max_tokens=1024, **kwargs):
        seen.append(list(messages))
        yield "Hi"

    engine.stream = stream
    return TestClient(create_app(engine, "test-model", config=_config(user_md)))


def test_empty_profile(client):
    assert client.get("/v1/profile").json() == {
        "first_name": "",
        "last_name": "",
        "nickname": "",
    }


def test_save_and_read_back(client, user_md):
    body = {"first_name": "Aryan", "last_name": "Kumar", "nickname": "Ary"}
    assert client.put("/v1/profile", json=body).json() == body
    assert client.get("/v1/profile").json() == body
    text = user_md.read_text(encoding="utf-8")
    assert text.startswith(START)
    assert 'Address the user as "Ary"' in text


def test_keeps_the_rest_of_user_md(client, user_md):
    user_md.write_text("I like short answers.\n", encoding="utf-8")
    client.put(
        "/v1/profile", json={"first_name": "Aryan", "last_name": "", "nickname": ""}
    )
    client.put(
        "/v1/profile", json={"first_name": "Aryan", "last_name": "", "nickname": "Ary"}
    )
    text = user_md.read_text(encoding="utf-8")
    assert text.count(START) == 1
    assert text.endswith("I like short answers.\n")

    client.put("/v1/profile", json={"first_name": "", "last_name": "", "nickname": ""})
    assert user_md.read_text(encoding="utf-8") == "I like short answers.\n"


def test_clearing_an_otherwise_empty_file_removes_it(client, user_md):
    client.put("/v1/profile", json={"first_name": "A", "last_name": "", "nickname": ""})
    client.put("/v1/profile", json={"first_name": "", "last_name": "", "nickname": ""})
    assert not user_md.exists()


def test_values_are_one_plain_line(client):
    resp = client.put(
        "/v1/profile",
        json={
            "first_name": "Ar\nyan",
            "last_name": "<!-- x -->",
            "nickname": "  Ary  ",
        },
    )
    assert resp.json() == {"first_name": "Ar yan", "last_name": "x", "nickname": "Ary"}


def test_rejects_long_names(client):
    assert client.put("/v1/profile", json={"nickname": "x" * 51}).status_code == 422


def test_first_name_is_used_without_a_nickname():
    block = render_block(Profile(first_name="Aryan", last_name="Kumar"))
    assert 'Address the user as "Aryan"' in block
    assert parse_block(f"before\n{block}after") == Profile(
        first_name="Aryan", last_name="Kumar"
    )
    assert render_block(Profile()) == ""
    assert END in block


def test_the_assistant_is_told_the_nickname(client, seen):
    client.put(
        "/v1/profile",
        json={"first_name": "Aryan", "last_name": "Kumar", "nickname": "Ary"},
    )
    client.post(
        "/v1/chat/completions",
        json={
            "model": "test-model",
            "messages": [{"role": "user", "content": "hello"}],
            "stream": True,
        },
    )
    system = [m for m in seen[0] if m.role == Role.SYSTEM]
    assert len(system) == 1
    assert "## User Profile" in system[0].content
    assert 'Address the user as "Ary"' in system[0].content


def test_persona_none_cannot_store_a_name(user_md):
    cfg = _config(user_md)
    cfg.memory_files.persona_name = "none"
    engine = MagicMock()
    client = TestClient(create_app(engine, "test-model", config=cfg))
    assert client.put("/v1/profile", json={"nickname": "Ary"}).status_code == 409
