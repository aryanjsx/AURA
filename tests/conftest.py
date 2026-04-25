"""Pytest bootstrap: ensure repo root is importable and config is loaded once."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Allow tests to import plugin executor code directly.
os.environ.setdefault("AURA_WORKER", "1")

from aura.core.config_loader import load_config  # noqa: E402

load_config()


# ── shared fixtures for the unit test suite ──────────────────────────


@pytest.fixture()
def sandbox_dir(tmp_path):
    """Provide a temporary sandbox directory and patch config to use it."""
    import aura.core.config_loader as cl
    import aura.security.sandbox as sb

    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()

    original_cache = cl._cache
    patched_cache = None
    if original_cache is not None:
        import copy
        patched_cache = copy.deepcopy(original_cache)
        patched_cache["sandbox"]["base_dir"] = str(sandbox)

    old_get = cl.get

    def _patched_get(key, default=None):
        if key == "sandbox.base_dir":
            return str(sandbox)
        if key == "paths.protected":
            return [
                "C:/Windows", "C:/Windows/System32",
                "C:/Program Files", "C:/Program Files (x86)",
                "/bin", "/usr", "/etc", "/sbin", "/boot",
            ]
        return old_get(key, default)

    sb.reset_base_dir_cache()
    with patch.object(cl, "get", side_effect=_patched_get):
        with patch.object(cl, "_cache", patched_cache):
            yield sandbox
    sb.reset_base_dir_cache()


@pytest.fixture()
def executor(sandbox_dir):
    """Return a SystemExecutor wired to a temp sandbox, with exported methods."""
    from aura.core.event_bus import EventBus
    from plugins.system.executor import SystemExecutor

    bus = EventBus()
    ex = SystemExecutor(bus)
    handlers = ex._export_executors()
    yield handlers


@pytest.fixture()
def event_bus():
    """Return a fresh EventBus (not the singleton)."""
    from aura.core.event_bus import EventBus
    return EventBus()


@pytest.fixture()
def fixtures_dir():
    """Return the path to the tests/fixtures directory."""
    return Path(__file__).resolve().parent / "fixtures"
