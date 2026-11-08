"""Listing and uninstalling local (Ollama) models."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

fastapi = pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from locus.server import routes  # noqa: E402
from locus.server.app import create_app  # noqa: E402

TAGS = {
    "models": [
        {
            "name": "qwen3.5:9b",
            "size": 6_600_000_000,
            "modified_at": "2026-11-09T10:00:00Z",
            "details": {"parameter_size": "9B"},
        },
        {"name": "qwen3.5:4b", "size": 3_400_000_000, "details": {}},
    ]
}


class FakeOllama:
    """Stands in for httpx.AsyncClient talking to Ollama."""

    deleted: list = []
    missing: set = set()
    down = False

    def __init__(self, base_url="", timeout=0):
        self.base_url = base_url

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def _response(self, method, path, status=200, body=None):
        request = httpx.Request(method, f"{self.base_url}{path}")
        return httpx.Response(status, json=body or {}, request=request)

    async def get(self, path):
        if self.down:
            raise httpx.ConnectError("refused")
        return self._response("GET", path, body=TAGS)

    async def request(self, method, path, json=None):
        if self.down:
            raise httpx.ConnectError("refused")
        name = json["name"]
        if name in self.missing:
            return self._response(method, path, 404, {"error": "model not found"})
        type(self).deleted.append(name)
        return self._response(method, path)


@pytest.fixture
def client(monkeypatch):
    FakeOllama.deleted = []
    FakeOllama.missing = set()
    FakeOllama.down = False
    monkeypatch.setattr(httpx, "AsyncClient", FakeOllama)
    engine = SimpleNamespace(engine_id="ollama", _host="http://ollama:11434")
    from locus.core.config import JarvisConfig

    cfg = JarvisConfig()
    cfg.analytics.enabled = False
    cfg.traces.enabled = False
    return TestClient(create_app(engine, "qwen3.5:4b", config=cfg))


def test_installed_models_have_sizes_and_the_default(client):
    body = client.get("/v1/models/installed").json()

    assert body["total_bytes"] == 10_000_000_000
    assert [m["name"] for m in body["models"]] == ["qwen3.5:4b", "qwen3.5:9b"]
    nine = body["models"][1]
    assert nine["size_bytes"] == 6_600_000_000
    assert nine["parameter_size"] == "9B"
    assert [m["is_default"] for m in body["models"]] == [True, False]


def test_uninstall_reports_the_space_freed(client):
    routes._vision_cache["qwen3.5:9b"] = True

    body = client.delete("/v1/models/qwen3.5:9b").json()

    assert body == {
        "status": "deleted",
        "model": "qwen3.5:9b",
        "freed_bytes": 6_600_000_000,
        "was_default": False,
    }
    assert FakeOllama.deleted == ["qwen3.5:9b"]
    assert "qwen3.5:9b" not in routes._vision_cache


def test_uninstalling_the_default_model_says_so(client):
    assert client.delete("/v1/models/qwen3.5:4b").json()["was_default"] is True


def test_uninstalling_a_missing_model_is_404(client):
    FakeOllama.missing = {"gone:1b"}
    resp = client.delete("/v1/models/gone:1b")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "gone:1b isn't installed."


def test_ollama_down_is_502(client):
    FakeOllama.down = True
    assert client.get("/v1/models/installed").status_code == 502
    assert client.delete("/v1/models/qwen3.5:9b").status_code == 502


def test_other_engines_cant_uninstall(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", FakeOllama)
    engine = SimpleNamespace(engine_id="vllm")
    from locus.core.config import JarvisConfig

    cfg = JarvisConfig()
    cfg.analytics.enabled = False
    cfg.traces.enabled = False
    client = TestClient(create_app(engine, "m", config=cfg))

    assert client.get("/v1/models/installed").status_code == 501
    assert client.delete("/v1/models/m").status_code == 501
