"""Tests for the canonical ``plugin.action`` fallback intent parser.

The parser lives in ``aura.intents.system_intents`` and is appended
LAST in ``default_intent_parsers()``.  These tests confirm:

* it recognises well-formed action ids and rejects junk;
* it produces intents that route through the full Registry safety
  pipeline (no bypass of rate limit / permission / safety gate);
* destructive actions via the action-id form still require confirm.
"""
from __future__ import annotations


from aura.core.event_bus import EventBus
from aura.core.result import CommandResult
from aura.intents import default_intent_parsers
from aura.intents.system_intents import parse_action_id
from aura.runtime.command_registry import CommandRegistry
from aura.runtime.execution_engine import ExecutionEngine
from aura.runtime.router import Router
from aura.security.permissions import PermissionLevel, PermissionValidator
from aura.security.plugin_manifest import PluginManifest
from aura.security.rate_limiter import RateLimiter
from aura.security.safety_gate import AutoConfirmGate, SafetyGate
from tests._inprocess_port import InProcessWorkerPort


# ---------------------------------------------------------------------------
# Unit tests on the parser itself.
# ---------------------------------------------------------------------------
class TestParseActionId:
    def test_zero_arg_action(self):
        intent = parse_action_id("system.cpu")
        assert intent is not None
        assert intent.action == "system.cpu"
        assert intent.args == {}
        assert intent.requires_confirm is False

    def test_keyword_args(self):
        intent = parse_action_id("file.create path=foo.txt")
        assert intent is not None
        assert intent.action == "file.create"
        assert intent.args == {"path": "foo.txt"}

    def test_integer_coercion_for_limit(self):
        intent = parse_action_id("file.search directory=. pattern=*.py limit=25")
        assert intent is not None
        assert intent.args["limit"] == 25
        assert isinstance(intent.args["limit"], int)

    def test_quoted_value_survives_spaces(self):
        intent = parse_action_id('process.shell command="git status"')
        assert intent is not None
        assert intent.args == {"command": "git status"}

    def test_destructive_action_sets_requires_confirm(self):
        intent = parse_action_id("file.delete path=x.txt")
        assert intent is not None
        assert intent.requires_confirm is True

    def test_non_dotted_word_rejected(self):
        assert parse_action_id("cpu") is None
        assert parse_action_id("help") is None

    def test_junk_rejected(self):
        assert parse_action_id("fly to mars") is None
        assert parse_action_id("") is None
        assert parse_action_id("   ") is None

    def test_unknown_key_passes_through_to_registry(self):
        # The parser used to swallow these and the router surfaced them
        # as "Unknown command".  We now let them through so the registry
        # can reject with a usage hint that names the valid keys.
        intent = parse_action_id("file.create target=foo.txt")
        assert intent is not None
        assert intent.action == "file.create"
        assert intent.args == {"target": "foo.txt"}

    def test_positional_arg_rejected_for_ambiguity(self):
        assert parse_action_id("file.create foo.txt") is None

    def test_duplicate_key_rejected(self):
        assert parse_action_id("file.create path=a path=b") is None

    def test_uppercase_action_rejected(self):
        # Action ids are lowercase by contract; refuse case variants to
        # avoid silent aliasing.
        assert parse_action_id("System.CPU") is None

    def test_unbalanced_quotes_return_none(self):
        # Don't crash, don't raise -- just let another parser try.
        assert parse_action_id('process.shell command="unterminated') is None

    def test_bad_int_returns_none(self):
        assert parse_action_id("file.search directory=. pattern=*.py limit=abc") is None

    def test_unknown_dotted_action_still_returned(self):
        # Not in PARAM_SCHEMAS; intent is still returned so the registry
        # can raise a clear "Unknown action" error.
        intent = parse_action_id("plugin.does_not_exist")
        assert intent is not None
        assert intent.action == "plugin.does_not_exist"

    def test_default_chain_contains_action_id_parser_last(self):
        parsers = default_intent_parsers()
        assert parsers[-1] is parse_action_id


# ---------------------------------------------------------------------------
# End-to-end: action-id input flows through the full safety pipeline.
# ---------------------------------------------------------------------------
def _build_router(
    *,
    auto_confirm: bool = True,
    rate_limiter=None,
    permission_validator=None,
    safety_gate=None,
):
    bus = EventBus()
    engine = ExecutionEngine(bus)

    class _Owner:
        pass
    owner = _Owner()

    def _cpu() -> CommandResult:
        return CommandResult(success=True, message="42%", data={"pct": 42})

    def _ram() -> CommandResult:
        return CommandResult(success=True, message="55%", data={"pct": 55})

    def _delete(path: str) -> CommandResult:
        return CommandResult(
            success=True, message=f"deleted {path}", data={"path": path}
        )

    engine.register("system.cpu", _cpu, plugin_instance=owner)
    engine.register("system.ram", _ram, plugin_instance=owner)
    engine.register("file.delete", _delete, plugin_instance=owner)

    registry = CommandRegistry(
        bus,
        InProcessWorkerPort(engine),
        manifest=PluginManifest.permissive(),
        auto_confirm=auto_confirm,
        rate_limiter=rate_limiter or RateLimiter(
            max_per_minute=1000, repeat_threshold=1000,
        ),
        permission_validator=permission_validator or PermissionValidator(),
        safety_gate=safety_gate or AutoConfirmGate(bus),
    )
    registry.register_metadata(
        "system.cpu", plugin="t", permission_level=PermissionLevel.LOW,
    )
    registry.register_metadata(
        "system.ram", plugin="t", permission_level=PermissionLevel.LOW,
    )
    registry.register_metadata(
        "file.delete", plugin="t",
        permission_level=PermissionLevel.HIGH, destructive=True,
    )

    router = Router(bus, registry, intent_parsers=default_intent_parsers())
    return router, bus


def test_action_id_system_ram_routes_successfully():
    router, _ = _build_router()
    result = router.route("system.ram", source="cli")
    assert result.success is True
    assert result.message == "55%"


def test_action_id_system_cpu_routes_successfully():
    router, _ = _build_router()
    result = router.route("system.cpu", source="cli")
    assert result.success is True
    assert result.data == {"pct": 42}


def test_action_id_file_delete_still_blocked_for_llm_source():
    """Security regression guard.

    The action-id form must not give untrusted sources (llm) a way
    around the per-source permission cap.  ``file.delete`` is HIGH,
    llm is capped at MEDIUM, so this must be PERMISSION_DENIED.
    """
    router, _ = _build_router()
    result = router.route("file.delete path=target.txt", source="llm")
    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"


def test_action_id_destructive_triggers_confirmation_flow():
    """Safety-gate regression guard.

    With auto_confirm=False and a non-auto gate the router must refuse
    (ConfirmationDenied / timeout) rather than silently executing.  We
    install a gate whose input_fn rejects all prompts to observe this
    deterministically.
    """
    bus = EventBus()

    # A gate whose prompt answer always 'cancels' (non-ACCEPTED token).
    gate = SafetyGate(bus, input_fn=lambda _prompt: "no", timeout=1.0)

    router, _ = _build_router(auto_confirm=False, safety_gate=gate)
    result = router.route("file.delete path=x.txt", source="cli")
    assert result.success is False
    # error_code here is CONFIRMATION_DENIED -- the precise string
    # comes from aura.core.errors.ConfirmationDenied.code.
    assert result.error_code in {"CONFIRMATION_DENIED", "CONFIRMATION_TIMEOUT"}


def test_nl_phrases_still_win_over_action_id_parser():
    """Ordering regression: natural language must still resolve first."""
    router, _ = _build_router()
    r1 = router.route("ram", source="cli")  # NL path
    r2 = router.route("system.ram", source="cli")  # action-id path
    assert r1.success and r2.success
    assert r1.data == r2.data  # same underlying executor


def test_unknown_nl_falls_through_to_unknown_command():
    router, _ = _build_router()
    result = router.route("fly to mars", source="cli")
    assert result.success is False
    assert result.error_code == "UNKNOWN_COMMAND"
