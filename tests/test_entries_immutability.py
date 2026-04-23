"""
Phase-3 hardening: registry._entries is a read-only view whose
underlying dict is reachable only via token-gated mutation helpers.

Attacks that must FAIL:
    * ``registry._entries[action] = evil_entry``
    * ``del registry._entries[action]``
    * ``registry._entries._mutate_set(wrong_token, ...)``
    * ``registry._entries._mutate_pop(wrong_token, ...)``
    * ``registry.unregister("probe", token=None)``
    * reading the raw dict via any attribute path.
"""
from __future__ import annotations

import pytest

from aura.core.errors import RegistryError
from aura.core.event_bus import EventBus
from aura.core.result import CommandResult
from aura.runtime.command_registry import (
    CommandRegistry,
    _ENTRIES_TOKEN,
)
from aura.runtime.execution_engine import ExecutionEngine
from aura.security.permissions import PermissionLevel
from aura.security.plugin_manifest import PluginManifest
from tests._inprocess_port import InProcessWorkerPort


def _build():
    bus = EventBus()
    engine = ExecutionEngine(bus)

    class _Owner:
        pass

    owner = _Owner()
    engine.register(
        "probe.low",
        lambda: CommandResult(True, "ok"),
        plugin_instance=owner,
    )
    port = InProcessWorkerPort(engine)
    registry = CommandRegistry(
        bus,
        port,
        manifest=PluginManifest.permissive(),
        auto_confirm=True,
    )
    registry.register_metadata(
        "probe.low", plugin="t", permission_level=PermissionLevel.LOW
    )
    return registry


# ---------------------------------------------------------------------
# Direct dict-like mutation on the view is banned.
# ---------------------------------------------------------------------
def test_setitem_on_entries_view_raises():
    registry = _build()
    with pytest.raises(RegistryError, match="immutable"):
        registry._entries["new.action"] = object()


def test_delitem_on_entries_view_raises():
    registry = _build()
    with pytest.raises(RegistryError, match="immutable"):
        del registry._entries["probe.low"]


# ---------------------------------------------------------------------
# Mutation helpers require the module-private token.
# ---------------------------------------------------------------------
def test_mutate_set_without_token_raises():
    registry = _build()
    with pytest.raises(RegistryError, match="internal token"):
        registry._entries._mutate_set(object(), "x", object())


def test_mutate_pop_without_token_raises():
    registry = _build()
    with pytest.raises(RegistryError, match="internal token"):
        registry._entries._mutate_pop(object(), "probe.low")


# ---------------------------------------------------------------------
# Attribute firewall: internal slots are not reachable from outside.
# ---------------------------------------------------------------------
def test_internal_data_slot_is_not_exposed():
    registry = _build()
    view = registry._entries
    # None of these common leak paths succeed.
    for name in (
        "_data",
        "__data",
        "_EntriesView__data",
        "data",
        "_dict",
    ):
        with pytest.raises(AttributeError):
            getattr(view, name)


def test_view_dir_does_not_leak_private_slot():
    registry = _build()
    names = dir(registry._entries)
    for forbidden in ("_data", "__data", "_EntriesView__data", "data"):
        assert forbidden not in names, (
            f"_EntriesView.__dir__ leaked private slot {forbidden!r}"
        )


def test_view_setattr_is_blocked():
    registry = _build()
    with pytest.raises(AttributeError, match="immutable"):
        registry._entries.some_new_attr = 42  # type: ignore[attr-defined]


# ---------------------------------------------------------------------
# Read-only API still works.
# ---------------------------------------------------------------------
def test_view_read_api_works():
    registry = _build()
    view = registry._entries
    assert view.has("probe.low")
    assert not view.has("probe.nope")
    assert "probe.low" in view
    assert "probe.low" in view.list()
    assert view["probe.low"].action == "probe.low"
    assert len(view) == 1
    actions = [e.action for e in view.values()]
    assert actions == ["probe.low"]


# ---------------------------------------------------------------------
# unregister() is token-gated.
# ---------------------------------------------------------------------
def test_unregister_without_token_raises():
    registry = _build()
    with pytest.raises(RegistryError, match="internal registry token"):
        registry.unregister("probe.low")


def test_unregister_with_wrong_token_raises():
    registry = _build()
    with pytest.raises(RegistryError, match="internal registry token"):
        registry.unregister("probe.low", token=object())


def test_unregister_with_correct_token_succeeds():
    registry = _build()
    assert registry.has("probe.low")
    removed = registry.unregister("probe.low", token=_ENTRIES_TOKEN)
    assert removed is True
    assert not registry.has("probe.low")


def test_unregister_unknown_action_returns_false():
    registry = _build()
    removed = registry.unregister(
        "does.not.exist", token=_ENTRIES_TOKEN
    )
    assert removed is False


# ---------------------------------------------------------------------
# The registry closure still only captures non-callable data after
# switching to the entries view.  This is an integration guard for the
# closure-walk invariant from Phase-3.
# ---------------------------------------------------------------------
def test_registry_closure_remains_safe_after_view_adoption():
    from aura.runtime.command_registry import assert_safe_closures
    registry = _build()
    assert_safe_closures(registry)
