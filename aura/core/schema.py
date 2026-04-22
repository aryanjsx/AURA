"""
AURA — Strict Command Schema.

Every command that enters :class:`~aura.runtime.command_registry.CommandRegistry`
must be shaped like::

    {
        "action": "<string>",          # dot-namespaced action id
        "params": { ... },             # kwargs for the handler
        "requires_confirm": <bool>     # safety flag (future ready)
    }

Missing fields or wrong types raise :class:`~aura.core.errors.SchemaError`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aura.core.errors import SchemaError
from aura.core.intent import Intent

# Hard ceiling on the action name length.  Oversized names would flow
# untruncated into logs, audit events, trace scopes and error strings
# (DoS-lite) and serve no legitimate purpose.  256 bytes is ~4x the
# longest real-world action we ship (``system.monitor_processes``).
MAX_ACTION_NAME_LEN = 256


@dataclass(frozen=True, slots=True)
class CommandSpec:
    """Validated command payload."""

    action: str
    params: dict[str, Any] = field(default_factory=dict)
    requires_confirm: bool = False

    def with_confirm(self, requires_confirm: bool) -> "CommandSpec":
        return CommandSpec(
            action=self.action,
            params=dict(self.params),
            requires_confirm=requires_confirm,
        )


def validate_command(payload: Any) -> CommandSpec:
    """Validate *payload* and return a :class:`CommandSpec`.

    Raises
    ------
    SchemaError
        If *payload* is not a dict, lacks ``action``, or carries
        incorrect types for ``params`` / ``requires_confirm``.
    """
    if not isinstance(payload, dict):
        raise SchemaError(
            f"Command payload must be a dict, got {type(payload).__name__}"
        )

    action = payload.get("action")
    if not isinstance(action, str) or not action.strip():
        raise SchemaError("Command payload missing required string field 'action'")
    if len(action) > MAX_ACTION_NAME_LEN:
        raise SchemaError(
            f"'action' name exceeds {MAX_ACTION_NAME_LEN} characters "
            f"(got {len(action)})"
        )

    params = payload.get("params", {})
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise SchemaError(
            f"'params' must be a dict, got {type(params).__name__}"
        )

    for key in params:
        if not isinstance(key, str):
            raise SchemaError(f"Parameter keys must be strings, got {key!r}")

    requires_confirm = payload.get("requires_confirm", False)
    if not isinstance(requires_confirm, bool):
        raise SchemaError(
            f"'requires_confirm' must be bool, got {type(requires_confirm).__name__}"
        )

    return CommandSpec(
        action=action.strip(),
        params=dict(params),
        requires_confirm=requires_confirm,
    )


def intent_to_spec(intent: Intent, *, destructive: bool = False) -> CommandSpec:
    """Translate an :class:`Intent` into a validated :class:`CommandSpec`."""
    return validate_command({
        "action": intent.action,
        "params": dict(intent.args),
        "requires_confirm": bool(intent.requires_confirm or destructive),
    })
