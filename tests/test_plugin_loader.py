"""Tests for :mod:`aura.core.plugin_loader`.

The loader is exercised in a test-only package called ``_aura_test_plugins``
that we build on the fly under ``tmp_path``.  Each test writes a
minimal plugin tree, makes the parent directory importable, and then
runs the loader against that tree.
"""
from __future__ import annotations

import importlib
import sys
import textwrap
from pathlib import Path

import pytest

from aura.core.audit_events import AuditEventRegistry
from aura.core.command_registry import CommandRegistry
from aura.core.errors import PluginError
from aura.core.event_bus import EventBus
from aura.core.execution_engine import ExecutionEngine
from aura.core.permissions import PermissionLevel
from aura.core.plugin_loader import PluginLoader
from aura.core.plugin_manifest import ManifestEntry, PluginManifest


_COUNTER = {"n": 0}


def _fresh_prefix() -> str:
    _COUNTER["n"] += 1
    return f"_aura_test_plugins_{_COUNTER['n']}"


def _write_plugin_tree(root: Path, name: str, plugin_py: str) -> Path:
    pkg = root / name
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "plugin.py").write_text(textwrap.dedent(plugin_py), encoding="utf-8")
    return pkg


@pytest.fixture
def loader_factory(tmp_path: Path):
    """Return a factory that wires up a PluginLoader rooted at *tmp_path*.

    Ensures sys.path contains tmp_path so the synthetic package is
    importable, and cleans everything up afterwards.
    """
    sys.path.insert(0, str(tmp_path))
    added_modules: list[str] = []

    def factory(
        prefix: str,
        *,
        manifest_entries: dict[str, ManifestEntry] | None = None,
    ) -> tuple[PluginLoader, CommandRegistry]:
        bus = EventBus()
        engine = ExecutionEngine(bus)
        manifest = PluginManifest(manifest_entries or {})
        registry = CommandRegistry(bus, engine, manifest=manifest)
        loader = PluginLoader(
            bus,
            registry,
            engine,
            package_prefix=prefix,
            manifest=manifest,
            audit_events=AuditEventRegistry(),
        )
        added_modules.append(prefix)
        return loader, registry

    yield factory

    # Tear down: remove synthetic packages from sys.modules AND sys.path
    for prefix in added_modules:
        for mod in [m for m in list(sys.modules) if m == prefix or m.startswith(prefix + ".")]:
            sys.modules.pop(mod, None)
    try:
        sys.path.remove(str(tmp_path))
    except ValueError:
        pass


# ------------------------------------------------------------------------
# happy path
# ------------------------------------------------------------------------
def test_valid_plugin_registers_actions_and_intents(loader_factory, tmp_path):
    prefix = _fresh_prefix()
    root = tmp_path / prefix
    _write_plugin_tree(
        root,
        "demo",
        """
        from aura.core.plugin_base import Plugin
        from aura.core.result import CommandResult
        from aura.core.permissions import PermissionLevel


        class Plugin(Plugin):
            def register_commands(self):
                def _ping():
                    return CommandResult(True, "pong")
                return {
                    "demo.ping": {
                        "handler": _ping,
                        "description": "health check",
                        "destructive": False,
                        "permission_level": PermissionLevel.LOW,
                    }
                }

            def register_intents(self):
                return []
        """,
    )
    loader, registry = loader_factory(
        prefix,
        manifest_entries={
            "demo.ping": ManifestEntry(
                plugin="demo",
                action="demo.ping",
                permission_level=PermissionLevel.LOW,
                destructive=False,
                audit_events=("command.executing", "command.completed"),
            ),
        },
    )
    [loaded] = loader.load_all(root)
    assert loaded.name == "demo"
    assert "demo.ping" in loaded.actions
    entry = registry.get("demo.ping")
    assert entry.description == "health check"
    assert entry.destructive is False


# ------------------------------------------------------------------------
# failure modes
# ------------------------------------------------------------------------
def test_missing_plugin_class_rejected(loader_factory, tmp_path):
    prefix = _fresh_prefix()
    root = tmp_path / prefix
    _write_plugin_tree(root, "noclass", "# no Plugin class at all\n")
    loader, _ = loader_factory(prefix)
    with pytest.raises(PluginError) as excinfo:
        loader.load_all(root)
    assert "Plugin" in str(excinfo.value)


def test_plugin_class_not_subclassing_base_rejected(loader_factory, tmp_path):
    prefix = _fresh_prefix()
    root = tmp_path / prefix
    _write_plugin_tree(
        root,
        "badbase",
        """
        class Plugin:
            def __init__(self, bus):
                self.bus = bus
            def register_commands(self):
                return {}
            def register_intents(self):
                return []
        """,
    )
    loader, _ = loader_factory(prefix)
    with pytest.raises(PluginError) as excinfo:
        loader.load_all(root)
    assert "subclass" in str(excinfo.value)


def test_broken_register_commands_raises_plugin_error(loader_factory, tmp_path):
    prefix = _fresh_prefix()
    root = tmp_path / prefix
    _write_plugin_tree(
        root,
        "broken",
        """
        from aura.core.plugin_base import Plugin

        class Plugin(Plugin):
            def register_commands(self):
                raise RuntimeError("kaboom")
            def register_intents(self):
                return []
        """,
    )
    loader, _ = loader_factory(prefix)
    with pytest.raises(PluginError) as excinfo:
        loader.load_all(root)
    assert "kaboom" in str(excinfo.value)


def test_non_dict_register_commands_rejected(loader_factory, tmp_path):
    prefix = _fresh_prefix()
    root = tmp_path / prefix
    _write_plugin_tree(
        root,
        "wrong_return",
        """
        from aura.core.plugin_base import Plugin

        class Plugin(Plugin):
            def register_commands(self):
                return ["not", "a", "dict"]
            def register_intents(self):
                return []
        """,
    )
    loader, _ = loader_factory(prefix)
    with pytest.raises(PluginError) as excinfo:
        loader.load_all(root)
    assert "dict" in str(excinfo.value)


def test_non_callable_handler_rejected(loader_factory, tmp_path):
    prefix = _fresh_prefix()
    root = tmp_path / prefix
    _write_plugin_tree(
        root,
        "nothandler",
        """
        from aura.core.plugin_base import Plugin

        class Plugin(Plugin):
            def register_commands(self):
                return {"demo.bad": {"handler": "not-callable"}}
            def register_intents(self):
                return []
        """,
    )
    loader, _ = loader_factory(prefix)
    with pytest.raises(PluginError) as excinfo:
        loader.load_all(root)
    assert "callable" in str(excinfo.value)


def test_unimportable_plugin_surfaces_plugin_error(loader_factory, tmp_path):
    prefix = _fresh_prefix()
    root = tmp_path / prefix
    _write_plugin_tree(
        root,
        "broken_import",
        "raise ImportError('syntax-fail')\n",
    )
    loader, _ = loader_factory(prefix)
    with pytest.raises(PluginError) as excinfo:
        loader.load_all(root)
    assert "Failed to import" in str(excinfo.value)


def test_duplicate_action_rejected(loader_factory, tmp_path):
    prefix = _fresh_prefix()
    root = tmp_path / prefix
    _write_plugin_tree(
        root,
        "dup1",
        """
        from aura.core.plugin_base import Plugin
        from aura.core.result import CommandResult

        class Plugin(Plugin):
            def register_commands(self):
                return {"shared.action": lambda: CommandResult(True, "a")}
            def register_intents(self):
                return []
        """,
    )
    _write_plugin_tree(
        root,
        "dup2",
        """
        from aura.core.plugin_base import Plugin
        from aura.core.result import CommandResult

        class Plugin(Plugin):
            def register_commands(self):
                return {"shared.action": lambda: CommandResult(True, "b")}
            def register_intents(self):
                return []
        """,
    )
    loader, _ = loader_factory(
        prefix,
        manifest_entries={
            # Register the action under *one* plugin so the first load
            # succeeds and the duplicate-registration guard is what
            # rejects the second.  (If we skipped the manifest entirely
            # the first load would fail with "unknown action".)
            "shared.action": ManifestEntry(
                plugin="dup1",
                action="shared.action",
                permission_level=PermissionLevel.MEDIUM,
                destructive=False,
                audit_events=("command.executing", "command.completed"),
            ),
        },
    )
    with pytest.raises(Exception) as excinfo:
        loader.load_all(root)
    # Either the CommandRegistry's duplicate guard or the manifest's
    # plugin-mismatch guard is acceptable — both prevent the second
    # registration.
    assert any(
        kw in str(excinfo.value).lower()
        for kw in ("duplicate", "owned by plugin")
    )


def test_non_callable_intent_parser_rejected(loader_factory, tmp_path):
    prefix = _fresh_prefix()
    root = tmp_path / prefix
    _write_plugin_tree(
        root,
        "intent_bad",
        """
        from aura.core.plugin_base import Plugin

        class Plugin(Plugin):
            def register_commands(self):
                return {}
            def register_intents(self):
                return ["not-callable"]
        """,
    )
    loader, _ = loader_factory(prefix)
    with pytest.raises(PluginError) as excinfo:
        loader.load_all(root)
    assert "callable" in str(excinfo.value)


def test_skips_underscore_and_pycache(loader_factory, tmp_path):
    """Hidden directories must not be treated as plugins."""
    prefix = _fresh_prefix()
    root = tmp_path / prefix
    (root / "__pycache__").mkdir(parents=True, exist_ok=True)
    (root / "__pycache__" / "plugin.py").write_text("raise RuntimeError('unreachable')")
    (root / "_staging").mkdir(parents=True, exist_ok=True)
    (root / "_staging" / "plugin.py").write_text("raise RuntimeError('unreachable')")

    loader, _ = loader_factory(prefix)
    # Should not raise — both are skipped.
    assert loader.discover(root) == []
