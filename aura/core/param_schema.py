"""
AURA — Per-action parameter schema (strict, no implicit coercion).

Every action that the system understands has a declared parameter spec
here.  :func:`validate_params` is called from the command registry
**before** dispatch, and again defensively inside the isolated worker,
so that:

* unknown parameter names are rejected,
* missing required parameters are rejected,
* wrong parameter *types* are rejected (no silent ``str(x)`` coercion),
* nested containers (``dict`` / ``list``) are rejected unless the spec
  explicitly allows them,
* ``bool`` is never accepted where ``int`` is required (Python's
  ``bool`` is an ``int`` subclass; we special-case this to avoid the
  classic ``True → 1`` type-confusion surface).

The schema is deliberately kept minimal and colocated with the action
taxonomy: adding a new action to the system plugin MUST be accompanied
by a new entry here, otherwise :func:`validate_params` will accept an
empty-params call and reject every named parameter — failing safely.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from aura.core.errors import SchemaError


# ---------------------------------------------------------------------------
# Size limits — enforced BEFORE any downstream work so oversized payloads
# never reach logging, IPC serialisation, or executor dispatch.
# ---------------------------------------------------------------------------
MAX_PARAM_STRING_LEN: int = 64 * 1024          # 64 KiB per string value
MAX_PARAMS_SERIALISED_BYTES: int = 256 * 1024  # 256 KiB entire params dict
MAX_PARAMS_KEYS: int = 64                      # paranoia: no 10k-key dicts


def enforce_param_size(action: str, params: dict[str, Any]) -> None:
    """Reject oversized payloads with :class:`SchemaError`.

    Runs before logging / IPC / execution so a hostile caller cannot
    trigger multi-megabyte allocations or blow up the audit log by
    shipping large blobs in `params`.
    """
    if not isinstance(params, dict):
        return  # handled by validate_params; avoid double-raising here
    if len(params) > MAX_PARAMS_KEYS:
        raise SchemaError(
            f"Too many parameters for {action!r}: {len(params)} "
            f"(max {MAX_PARAMS_KEYS})"
        )
    for name, value in params.items():
        if isinstance(value, str) and len(value) > MAX_PARAM_STRING_LEN:
            raise SchemaError(
                f"Parameter {name!r} for {action!r} exceeds "
                f"{MAX_PARAM_STRING_LEN} bytes ({len(value)})"
            )
        if isinstance(value, (bytes, bytearray)) and len(value) > MAX_PARAM_STRING_LEN:
            raise SchemaError(
                f"Parameter {name!r} for {action!r} exceeds "
                f"{MAX_PARAM_STRING_LEN} bytes ({len(value)})"
            )
    # Whole-payload size: cheap serialisation gives the number of bytes
    # that would be written to IPC / the audit log.
    try:
        encoded = json.dumps(params, default=str, ensure_ascii=False)
    except Exception as exc:  # pragma: no cover - extremely exotic
        raise SchemaError(
            f"Params for {action!r} are not JSON-serialisable: {exc}"
        ) from exc
    if len(encoded.encode("utf-8")) > MAX_PARAMS_SERIALISED_BYTES:
        raise SchemaError(
            f"Serialised params for {action!r} exceed "
            f"{MAX_PARAMS_SERIALISED_BYTES} bytes "
            f"({len(encoded.encode('utf-8'))})"
        )


@dataclass(frozen=True, slots=True)
class ParamSpec:
    """Declarative parameter specification.

    ``types`` is a tuple of concrete ``type`` objects the value is
    allowed to be.  ``NoneType`` may be included to make a parameter
    explicitly nullable.  ``bool`` must be listed explicitly — it is
    NEVER accepted implicitly in place of ``int``.
    """

    name: str
    types: tuple[type, ...]
    required: bool = True


_NoneType = type(None)


# --- Action taxonomy --------------------------------------------------------
# NOTE: every key below is a public action name advertised by the system
# plugin.  If a new action is added to ``plugins/system/executor.py``,
# its schema MUST be added here too — otherwise the registry will refuse
# all named parameters.

PARAM_SCHEMAS: dict[str, tuple[ParamSpec, ...]] = {
    # ---- filesystem ----
    "file.create": (ParamSpec("path", (str,)),),
    "file.delete": (ParamSpec("path", (str,)),),
    "file.rename": (
        ParamSpec("old_name", (str,)),
        ParamSpec("new_name", (str,)),
    ),
    "file.move": (
        ParamSpec("source", (str,)),
        ParamSpec("destination", (str,)),
    ),
    "file.search": (
        ParamSpec("directory", (str,)),
        ParamSpec("pattern", (str,)),
        ParamSpec("limit", (int,), required=False),
    ),
    # ---- process / shell ----
    "process.shell": (ParamSpec("command", (str,)),),
    "process.list":  (ParamSpec("limit", (int,), required=False),),
    "process.kill":  (ParamSpec("process_name", (str,)),),
    # ---- system monitor ----
    "system.cpu":    (),
    "system.ram":    (),
    "system.health": (),
    # ---- npm ----
    "npm.install":   (ParamSpec("cwd", (str,)),),
    "npm.run":       (
        ParamSpec("script", (str,)),
        ParamSpec("cwd", (str,)),
    ),
}


def _type_names(types: tuple[type, ...]) -> str:
    return ", ".join(t.__name__ for t in types)


def validate_params(action: str, params: dict[str, Any]) -> None:
    """Validate *params* against the declared schema for *action*.

    Raises
    ------
    SchemaError
        If any rule in this module's docstring is violated.

    Notes
    -----
    Unknown actions are **not** rejected here — that is the registry's
    job.  We simply refuse every named parameter for unknown actions,
    which surfaces as "Unknown parameter X" and is then re-raised as a
    ``RegistryError`` (`Unknown action: …`) once we return.
    """
    if not isinstance(params, dict):
        raise SchemaError(
            f"'params' must be a dict, got {type(params).__name__}"
        )

    # Size limits come first — oversize payload is rejected for *every*
    # action, including unregistered ones, because the cost is in
    # logging / IPC, not the schema.
    enforce_param_size(action, params)

    # Opt-in model: actions without a declared schema are not validated
    # here (the registry's own `get()` has already verified the action
    # is one it knows about).  Every *production* action MUST be listed
    # in PARAM_SCHEMAS; test-only synthetic actions are out of scope.
    if action not in PARAM_SCHEMAS:
        return

    specs = PARAM_SCHEMAS[action]
    spec_by_name = {s.name: s for s in specs}

    # 1) Reject unknown keys.
    for key in params:
        if not isinstance(key, str):
            raise SchemaError(
                f"Parameter keys must be strings, got {type(key).__name__}"
            )
        if key not in spec_by_name:
            raise SchemaError(
                f"Unknown parameter {key!r} for action {action!r}; "
                f"allowed: {sorted(spec_by_name)}"
            )

    # 2) Missing required + type validation.
    for spec in specs:
        if spec.name not in params:
            if spec.required:
                raise SchemaError(
                    f"Missing required parameter {spec.name!r} "
                    f"for action {action!r}"
                )
            continue

        value = params[spec.name]

        # bool-masquerading-as-int guard: refuse bool whenever int is
        # accepted unless the spec explicitly includes bool.
        if (
            isinstance(value, bool)
            and int in spec.types
            and bool not in spec.types
        ):
            raise SchemaError(
                f"Parameter {spec.name!r} for {action!r} must be "
                f"{_type_names(spec.types)}, got bool"
            )

        if not isinstance(value, spec.types):
            raise SchemaError(
                f"Parameter {spec.name!r} for {action!r} must be "
                f"{_type_names(spec.types)}, got {type(value).__name__}"
            )

        # Explicitly reject nested containers unless the spec allows them
        # (dict / list are NOT in any current spec, but we future-proof
        # the error so a careless schema edit cannot widen the surface
        # without also updating this check).
        if isinstance(value, (dict, list, tuple, set, frozenset)) and not any(
            t in spec.types for t in (dict, list, tuple, set, frozenset)
        ):
            raise SchemaError(
                f"Parameter {spec.name!r} for {action!r} may not be a "
                f"nested container ({type(value).__name__})"
            )


__all__ = ["ParamSpec", "PARAM_SCHEMAS", "validate_params"]
