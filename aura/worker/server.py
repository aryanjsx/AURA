"""
AURA Execution Worker — JSON-line IPC server.

The worker is a separate subprocess spawned by the main AURA process.
Plugin executors live ONLY here.  The main process never imports
``plugins.*`` and therefore cannot be compromised by a malicious plugin.

Startup
-------
1. Restrict our own ``os.environ`` to a minimal allowlist.
2. Load config, build an event bus, ExecutionEngine, stub CommandRegistry.
3. Discover and load plugins.
4. Emit a ``ready`` record on stdout carrying the full action schema.
5. Enter the request loop.

Request / response protocol (one JSON object per line)
------------------------------------------------------
- client → worker:
    {"type": "exec",
     "id":   "<request-id>",
     "action": "file.create",
     "params": {...},
     "trace_id": "..."}
- worker → client (success):
    {"type": "result", "id": "<request-id>",
     "success": true, "message": "...", "data": {...},
     "command_type": "...", "error_code": null}
- worker → client (failure):
    {"type": "error", "id": "<request-id>",
     "error_class": "SandboxError", "error_code": "SANDBOX_ERROR",
     "message": "..."}
- client → worker shutdown:
    {"type": "shutdown"}

Hardening
---------
- JSON only.  ``pickle`` / ``eval`` / ``exec`` / dynamic ``__import__``
  are never used on incoming payloads.
- stdin is the ONLY command channel.
- stderr receives the worker's JSON log; stdout is reserved for the IPC
  protocol so logs and results never interleave.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import traceback
from pathlib import Path
from typing import Any, IO

_ALLOWED_ENV_KEYS: frozenset[str] = frozenset({
    # Keep only what Python/OS *must* have to run; drop everything else.
    "PATH", "PATHEXT", "PYTHONPATH", "PYTHONHOME", "PYTHONIOENCODING",
    "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "TEMP", "TMP", "COMSPEC",
    "HOME", "USERPROFILE", "USERNAME", "LOGNAME", "LANG", "LC_ALL",
    "AURA_LOG_PATH", "AURA_SHELL_TIMEOUT",
    "AURA_PROTECTED_PATHS", "AURA_SANDBOX_DIR",
    "AURA_WORKER", "AURA_MANIFEST_SHA256",
    "LOCALAPPDATA", "APPDATA",
})


def _restrict_environment() -> None:
    """Strip every env var except the safe allowlist."""
    to_drop = [k for k in list(os.environ.keys()) if k.upper() not in _ALLOWED_ENV_KEYS]
    for k in to_drop:
        try:
            del os.environ[k]
        except KeyError:
            pass


def _ensure_repo_on_syspath() -> None:
    """Make sure the repo root is importable (we were spawned with ``-m``)."""
    root = Path(__file__).resolve().parent.parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def _worker_log(stderr: IO[str], level: str, event: str, **extra: Any) -> None:
    payload = {"worker": True, "pid": os.getpid(), "level": level, "event": event}
    payload.update(extra)
    try:
        stderr.write(json.dumps(payload, default=str) + "\n")
        stderr.flush()
    except Exception:
        pass


def _send(stream: IO[str], message: dict[str, Any]) -> None:
    stream.write(json.dumps(message, default=str) + "\n")
    stream.flush()


class _MetadataSink:
    """Minimal registry stand-in used ONLY inside the worker.

    Satisfies the subset of the :class:`CommandRegistry` contract that
    :class:`PluginLoader` needs (``register_metadata`` + ``list``).  The
    worker deliberately avoids building a real :class:`CommandRegistry`
    because doing so would seal the in-process :class:`ExecutionEngine`
    and hand its dispatch capability to the wrong owner — the worker's
    IPC loop, not the main-process registry.
    """

    def __init__(self) -> None:
        self._entries: list[dict[str, Any]] = []

    def register_metadata(
        self,
        action: str,
        *,
        plugin: str,
        description: str = "",
        destructive: bool = False,
        permission_level: Any = None,
    ) -> None:
        from aura.security.permissions import PermissionLevel  # noqa: WPS433

        level = PermissionLevel.parse(permission_level)
        self._entries.append({
            "action": action,
            "plugin": plugin,
            "description": description,
            "destructive": bool(destructive),
            "permission_level": level.value,
        })

    def list(self) -> list[dict[str, Any]]:
        return list(self._entries)


def _verify_manifest_hash() -> None:
    """Refuse to boot if the parent manifest hash doesn't match ours.

    The main process publishes ``AURA_MANIFEST_SHA256`` after hashing
    ``plugins_manifest.yaml``.  The worker recomputes the hash locally
    and bails out hard on mismatch — a swapped manifest file in the
    worker's filesystem view cannot loosen the trust boundary.
    """
    from aura.security.plugin_manifest import (  # noqa: WPS433
        default_manifest_path,
        manifest_sha256,
        PluginManifestError,
    )

    expected = os.environ.get("AURA_MANIFEST_SHA256", "").strip().lower()
    if not expected:
        raise RuntimeError(
            "AURA_MANIFEST_SHA256 missing — worker refuses to boot without "
            "a parent-bound manifest hash"
        )
    try:
        local = manifest_sha256(
            default_manifest_path(Path(__file__).resolve().parent.parent.parent)
        ).lower()
    except PluginManifestError as exc:
        raise RuntimeError(f"Worker cannot read local manifest: {exc}") from exc
    if local != expected:
        raise RuntimeError(
            "Manifest hash mismatch between main process and worker: "
            f"parent={expected!r} local={local!r} — refusing to start"
        )


def _build_engine_and_sink():
    """Lazy-import AURA internals AFTER env restriction."""
    from aura.core.config_loader import load_config
    from aura.core.event_bus import get_event_bus
    from aura.runtime.execution_engine import ExecutionEngine
    from aura.core.plugin_loader import PluginLoader
    from aura.security.plugin_manifest import PluginManifest, default_manifest_path
    from aura.core.tracing import set_trace_id

    load_config()
    bus = get_event_bus()
    engine = ExecutionEngine(bus)
    sink = _MetadataSink()

    _attach_worker_logger(bus)

    project_root = Path(__file__).resolve().parent.parent.parent
    manifest = PluginManifest.load(default_manifest_path(project_root))
    plugins_dir = project_root / "plugins"

    loader = PluginLoader(
        bus,
        sink,  # duck-typed — PluginLoader only calls register_metadata / list
        engine,
        package_prefix="plugins",
        manifest=manifest,
    )
    loader.load_all(plugins_dir)

    # Seal the engine ourselves — we are the only legitimate dispatcher
    # holder inside the worker process.
    dispatch = engine._seal()

    return engine, sink, dispatch, bus, set_trace_id


def _attach_worker_logger(bus) -> None:
    """Route bus events to stderr so IPC stdout stays clean."""
    from aura.core.logger import JSONFormatter, attach_event_bus_logger, get_logger  # noqa: WPS433

    logger = get_logger("aura")
    # Strip any default handlers that might write to stdout (we reserve
    # stdout exclusively for the IPC protocol).
    for h in list(logger.handlers):
        stream = getattr(h, "stream", None)
        if stream is sys.stdout:
            logger.removeHandler(h)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(JSONFormatter())
    logger.addHandler(stderr_handler)

    attach_event_bus_logger(bus, logger)


def _action_schema(sink) -> list[dict[str, Any]]:
    return [
        {
            "action": entry["action"],
            "plugin": entry["plugin"],
            "description": entry["description"],
            "destructive": entry["destructive"],
            "permission_level": entry["permission_level"],
        }
        for entry in sink.list()
    ]


def _handle_exec(dispatch, set_trace_id, request: dict[str, Any]) -> dict[str, Any]:
    request_id = request.get("id")
    action = request.get("action")
    params = request.get("params") or {}
    trace_id = request.get("trace_id")

    if not isinstance(action, str) or not action.strip():
        return {
            "type": "error",
            "id": request_id,
            "error_class": "SchemaError",
            "error_code": "SCHEMA_ERROR",
            "message": "Missing or empty 'action' field",
        }
    if not isinstance(params, dict):
        return {
            "type": "error",
            "id": request_id,
            "error_class": "SchemaError",
            "error_code": "SCHEMA_ERROR",
            "message": "'params' must be a JSON object",
        }

    if trace_id:
        set_trace_id(str(trace_id))

    # Defence-in-depth: the registry in the *main* process already
    # rejected invalid params, but a worker that trusts its caller is
    # a worker that falls over the first time the caller has a bug.
    try:
        from aura.core.param_schema import validate_params
        validate_params(action, dict(params))
    except Exception as exc:
        from aura.core.errors import SchemaError
        err = exc if isinstance(exc, SchemaError) else SchemaError(str(exc))
        return {
            "type": "error",
            "id": request_id,
            "error_class": "SchemaError",
            "error_code": "SCHEMA_ERROR",
            "message": str(err),
        }

    try:
        result = dispatch(action, dict(params))
    except Exception as exc:  # noqa: BLE001 — worker IPC boundary
        from aura.core.errors import AuraError

        error_code = "EXECUTION_ERROR"
        error_class = type(exc).__name__
        if isinstance(exc, AuraError):
            try:
                from aura.core.error_handler import _classify  # noqa: WPS450

                error_code = _classify(exc)
            except Exception:
                pass
        return {
            "type": "error",
            "id": request_id,
            "error_class": error_class,
            "error_code": error_code,
            "message": str(exc),
        }

    return {
        "type": "result",
        "id": request_id,
        "success": bool(result.success),
        "message": str(result.message),
        "data": dict(result.data or {}),
        "command_type": result.command_type or action,
        "error_code": result.error_code,
    }


def run_worker(
    stdin: IO[str],
    stdout: IO[str],
    stderr: IO[str],
) -> int:
    """Main worker loop.  Returns a process exit code."""
    # Capture the parent-bound hash BEFORE we strip env (we allowlist
    # AURA_MANIFEST_SHA256 already, so this is belt-and-braces).
    expected_hash = os.environ.get("AURA_MANIFEST_SHA256", "")
    _restrict_environment()
    if expected_hash and not os.environ.get("AURA_MANIFEST_SHA256"):
        os.environ["AURA_MANIFEST_SHA256"] = expected_hash
    _ensure_repo_on_syspath()

    try:
        _verify_manifest_hash()
        _engine, sink, dispatch, _bus, set_trace_id = _build_engine_and_sink()
        # ``_engine`` is kept on the stack so the dispatch bound method
        # has a live self reference (no-op for GC, but explicit).
    except Exception as exc:  # noqa: BLE001 — bootstrap failure is fatal
        _worker_log(
            stderr, "ERROR", "worker.bootstrap_failed",
            error=str(exc), traceback=traceback.format_exc(),
        )
        _send(stdout, {
            "type": "ready_failed",
            "error_class": type(exc).__name__,
            "message": str(exc),
        })
        return 2

    _send(stdout, {
        "type": "ready",
        "pid": os.getpid(),
        "actions": _action_schema(sink),
    })

    for raw in stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                raise ValueError("request must be a JSON object")
        except Exception as exc:
            _send(stdout, {
                "type": "error",
                "id": None,
                "error_class": "SchemaError",
                "error_code": "SCHEMA_ERROR",
                "message": f"Malformed request: {exc}",
            })
            continue

        msg_type = request.get("type")
        if msg_type == "shutdown":
            _worker_log(stderr, "INFO", "worker.shutdown")
            return 0
        if msg_type != "exec":
            _send(stdout, {
                "type": "error",
                "id": request.get("id"),
                "error_class": "SchemaError",
                "error_code": "SCHEMA_ERROR",
                "message": f"Unknown message type: {msg_type!r}",
            })
            continue

        reply = _handle_exec(dispatch, set_trace_id, request)
        _send(stdout, reply)

    return 0
