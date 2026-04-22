"""
Phase-2 hardening: the plugin safety manifest is the source of truth
for every action's permission level and destructive flag.  Plugins
cannot self-declare trust.
"""
from __future__ import annotations

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
from aura.core.plugin_manifest import (
    ManifestEntry,
    PluginManifest,
    PluginManifestError,
)


# ------------------------------------------------------------------
# Manifest parser
# ------------------------------------------------------------------
def test_manifest_rejects_missing_file(tmp_path: Path):
    with pytest.raises(PluginManifestError):
        PluginManifest.load(tmp_path / "does_not_exist.yaml")


def test_manifest_rejects_destructive_without_audit_events(tmp_path: Path):
    p = tmp_path / "m.yaml"
    p.write_text(
        textwrap.dedent(
            """
            version: 1
            plugins:
              sys:
                actions:
                  foo:
                    permission_level: HIGH
                    destructive: true
                    audit_events: []
            """
        ),
        encoding="utf-8",
    )
    with pytest.raises(PluginManifestError) as excinfo:
        PluginManifest.load(p)
    assert "audit_events" in str(excinfo.value)


def test_manifest_rejects_invalid_permission_level(tmp_path: Path):
    p = tmp_path / "m.yaml"
    p.write_text(
        textwrap.dedent(
            """
            version: 1
            plugins:
              sys:
                actions:
                  foo:
                    permission_level: GODMODE
                    destructive: false
            """
        ),
        encoding="utf-8",
    )
    with pytest.raises(PluginManifestError):
        PluginManifest.load(p)


def test_manifest_rejects_duplicate_action(tmp_path: Path):
    p = tmp_path / "m.yaml"
    p.write_text(
        textwrap.dedent(
            """
            version: 1
            plugins:
              a:
                actions:
                  shared.action:
                    permission_level: LOW
                    destructive: false
              b:
                actions:
                  shared.action:
                    permission_level: LOW
                    destructive: false
            """
        ),
        encoding="utf-8",
    )
    with pytest.raises(PluginManifestError):
        PluginManifest.load(p)


# ------------------------------------------------------------------
# Manifest.check — plugin lies about permission
# ------------------------------------------------------------------
def test_check_rejects_permission_mismatch():
    m = PluginManifest(
        {
            "x.action": ManifestEntry(
                plugin="x",
                action="x.action",
                permission_level=PermissionLevel.HIGH,
                destructive=False,
                audit_events=("command.executing",),
            ),
        }
    )
    with pytest.raises(PluginManifestError):
        m.check(
            plugin="x",
            action="x.action",
            permission_level=PermissionLevel.LOW,  # LIES
            destructive=False,
        )


def test_check_rejects_destructive_flag_mismatch():
    m = PluginManifest(
        {
            "x.rm": ManifestEntry(
                plugin="x",
                action="x.rm",
                permission_level=PermissionLevel.HIGH,
                destructive=True,
                audit_events=("command.destructive",),
            ),
        }
    )
    with pytest.raises(PluginManifestError):
        m.check(
            plugin="x",
            action="x.rm",
            permission_level=PermissionLevel.HIGH,
            destructive=False,  # LIES — says safe, manifest says destructive
        )


def test_check_rejects_unknown_plugin_owner():
    m = PluginManifest(
        {
            "x.a": ManifestEntry(
                plugin="x",
                action="x.a",
                permission_level=PermissionLevel.LOW,
                destructive=False,
                audit_events=("command.executing",),
            ),
        }
    )
    with pytest.raises(PluginManifestError):
        m.check(
            plugin="attacker",
            action="x.a",
            permission_level=PermissionLevel.LOW,
            destructive=False,
        )


# ------------------------------------------------------------------
# End-to-end: PluginLoader refuses a lying plugin
# ------------------------------------------------------------------
@pytest.fixture
def loader_env(tmp_path: Path):
    sys.path.insert(0, str(tmp_path))
    added: list[str] = []

    def build(prefix: str, manifest_entries: dict[str, ManifestEntry]):
        bus = EventBus()
        engine = ExecutionEngine(bus)
        manifest = PluginManifest(manifest_entries)
        registry = CommandRegistry(bus, engine, manifest=manifest)
        loader = PluginLoader(
            bus,
            registry,
            engine,
            package_prefix=prefix,
            manifest=manifest,
            audit_events=AuditEventRegistry(),
        )
        added.append(prefix)
        return loader, registry

    yield build

    for prefix in added:
        for mod in [m for m in list(sys.modules) if m == prefix or m.startswith(prefix + ".")]:
            sys.modules.pop(mod, None)
    try:
        sys.path.remove(str(tmp_path))
    except ValueError:
        pass


def _write_plugin(root: Path, name: str, body: str) -> Path:
    pkg = root / name
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "plugin.py").write_text(textwrap.dedent(body), encoding="utf-8")
    return pkg


_COUNTER = {"n": 0}


def _fresh(prefix: str = "_aura_manifest") -> str:
    _COUNTER["n"] += 1
    return f"{prefix}_{_COUNTER['n']}"


def test_loader_rejects_plugin_declaring_unknown_action(loader_env, tmp_path):
    prefix = _fresh()
    root = tmp_path / prefix
    _write_plugin(
        root,
        "liar",
        """
        from aura.core.plugin_base import Plugin
        from aura.core.result import CommandResult
        from aura.core.permissions import PermissionLevel

        class Plugin(Plugin):
            def register_commands(self):
                return {
                    "liar.hidden": {
                        "handler": lambda: CommandResult(True, "ok"),
                        "permission_level": PermissionLevel.LOW,
                        "destructive": False,
                    }
                }
            def register_intents(self):
                return []
        """,
    )
    loader, _ = loader_env(prefix, {})  # empty manifest
    with pytest.raises(PluginError) as excinfo:
        loader.load_all(root)
    assert "unknown action" in str(excinfo.value).lower()


def test_loader_rejects_plugin_lying_about_permission_level(
    loader_env, tmp_path
):
    prefix = _fresh()
    root = tmp_path / prefix
    _write_plugin(
        root,
        "liar",
        """
        from aura.core.plugin_base import Plugin
        from aura.core.result import CommandResult
        from aura.core.permissions import PermissionLevel

        class Plugin(Plugin):
            def register_commands(self):
                return {
                    "liar.sneak": {
                        "handler": lambda: CommandResult(True, "ok"),
                        "permission_level": PermissionLevel.LOW,   # LIES
                        "destructive": False,
                    }
                }
            def register_intents(self):
                return []
        """,
    )
    manifest = {
        "liar.sneak": ManifestEntry(
            plugin="liar",
            action="liar.sneak",
            permission_level=PermissionLevel.CRITICAL,   # truth
            destructive=False,
            audit_events=("command.executing",),
        ),
    }
    loader, _ = loader_env(prefix, manifest)
    with pytest.raises(PluginError) as excinfo:
        loader.load_all(root)
    assert "permission_level" in str(excinfo.value)


def test_loader_rejects_plugin_lying_about_destructive_flag(
    loader_env, tmp_path
):
    prefix = _fresh()
    root = tmp_path / prefix
    _write_plugin(
        root,
        "stealth",
        """
        from aura.core.plugin_base import Plugin
        from aura.core.result import CommandResult
        from aura.core.permissions import PermissionLevel

        class Plugin(Plugin):
            def register_commands(self):
                return {
                    "stealth.rm": {
                        "handler": lambda path: CommandResult(True, "ok"),
                        "permission_level": PermissionLevel.HIGH,
                        "destructive": False,     # LIES
                    }
                }
            def register_intents(self):
                return []
        """,
    )
    manifest = {
        "stealth.rm": ManifestEntry(
            plugin="stealth",
            action="stealth.rm",
            permission_level=PermissionLevel.HIGH,
            destructive=True,                           # truth
            audit_events=("command.destructive",),
        ),
    }
    loader, _ = loader_env(prefix, manifest)
    with pytest.raises(PluginError) as excinfo:
        loader.load_all(root)
    assert "destructive" in str(excinfo.value)


# ------------------------------------------------------------------
# The real shipped manifest must still cover every action the system
# plugin advertises.  This catches "forgot to update the manifest"
# regressions at CI time.
# ------------------------------------------------------------------
def test_shipped_manifest_matches_system_plugin():
    root = Path(__file__).resolve().parents[1]
    manifest = PluginManifest.load(root / "plugins_manifest.yaml")

    # Import the system plugin's register_commands WITHOUT running it
    # (it needs a bus), so just parse the action names from source.
    plugin_py = (root / "plugins" / "system" / "plugin.py").read_text(
        encoding="utf-8"
    )
    for expected in [
        "file.create", "file.delete", "file.rename", "file.move",
        "file.search", "process.shell", "process.list", "process.kill",
        "system.cpu", "system.ram", "system.health",
        "npm.install", "npm.run",
    ]:
        assert f'"{expected}"' in plugin_py, expected
        assert manifest.get(expected) is not None, expected
