"""
AURA — WorkerClient (locked down).

Main-process proxy that talks to the isolated execution worker
(:mod:`aura.worker.server`) over stdin/stdout JSON lines.

Lockdown model
--------------
The client exposes a :meth:`_seal` one-shot capability (consumed by
:class:`~aura.core.command_registry.CommandRegistry`) and NO public
``dispatch`` method.  The actual dispatch is name-mangled
(``_WorkerClient__dispatch``); after the registry has sealed the
client, no supported API returns the dispatcher — not ``bootstrap``,
not a public attribute, not a method.

Isolation invariants
--------------------
* Main never imports ``plugins.*``.
* Commands serialised as plain JSON (no ``pickle``).
* Worker crash → synthetic :class:`EngineError` result, then lazy
  respawn on the next call.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from typing import Callable

from aura.core.errors import EngineError, ExecutionError
from aura.core.event_bus import EventBus
from aura.core.logger import get_logger
from aura.core.plugin_manifest import manifest_sha256, default_manifest_path
from aura.core.result import CommandResult
from aura.core.tracing import current_trace_id


_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

_DEFAULT_TIMEOUT = 30.0

# Error-code mirror so worker responses translate to the same codes the
# in-process pipeline used to emit.
_ERROR_CLASS_TO_EXC: dict[str, type] = {}


def _import_exc_map() -> dict[str, type]:
    """Lazy — avoids circular imports at module load."""
    global _ERROR_CLASS_TO_EXC
    if _ERROR_CLASS_TO_EXC:
        return _ERROR_CLASS_TO_EXC
    from aura.core import errors as E

    _ERROR_CLASS_TO_EXC = {
        "AuraError": E.AuraError,
        "PluginError": E.PluginError,
        "RegistryError": E.RegistryError,
        "ExecutionError": E.ExecutionError,
        "PolicyError": E.PolicyError,
        "SandboxError": E.SandboxError,
        "ConfigError": E.ConfigError,
        "PermissionDenied": E.PermissionDenied,
        "ConfirmationDenied": E.ConfirmationDenied,
        "ConfirmationTimeout": E.ConfirmationTimeout,
        "RateLimitError": E.RateLimitError,
        "PlanError": E.PlanError,
        "EngineError": E.EngineError,
    }
    return _ERROR_CLASS_TO_EXC


class WorkerClient:
    """Owns the worker subprocess lifecycle and performs JSON-line RPC."""

    def __init__(
        self,
        bus: EventBus,
        *,
        python_executable: str | None = None,
        timeout: float | None = None,
        project_root: Path | None = None,
    ) -> None:
        self._bus = bus
        self._python = python_executable or sys.executable
        self._timeout = float(timeout) if timeout is not None else _DEFAULT_TIMEOUT
        self._root = project_root or _PROJECT_ROOT

        self._logger = get_logger("aura.worker_client")
        self._lock = threading.Lock()
        self._proc: subprocess.Popen[str] | None = None
        self._actions: dict[str, dict[str, Any]] = {}
        self.__sealed: bool = False
        self._manifest_hash: str | None = None

    # ---- lifecycle ------------------------------------------------------
    def start(self) -> list[dict[str, Any]]:
        """Spawn the worker and return its advertised action schema."""
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                return list(self._actions.values())
            self._spawn()
            return list(self._actions.values())

    def _spawn(self) -> None:
        # Restrict the child env aggressively — worker does its own
        # second-pass restriction but belt-and-braces here.
        env = self._restricted_env()

        # Do NOT pass ``-I`` / ``-E``: those disable ``PYTHONPATH``, which
        # we rely on to let the worker find ``aura``.  The environment is
        # already stripped by :meth:`_restricted_env` — that is the
        # isolation layer.  ``-s`` keeps user-site out of ``sys.path``.
        cmd = [self._python, "-s", "-m", "aura.worker"]
        self._logger.info(
            "worker.spawn",
            extra={"event": "worker.spawn", "cmd": cmd, "cwd": str(self._root)},
        )

        proc = subprocess.Popen(  # noqa: S603 — argv list, no shell
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(self._root),
            env=env,
            text=True,
            bufsize=1,
            shell=False,
        )

        ready_line = self._read_line(proc, self._timeout)
        if ready_line is None:
            proc.kill()
            stderr_tail = self._drain_stderr(proc)
            raise EngineError(
                f"Worker failed to start (no ready line). stderr: {stderr_tail}"
            )

        try:
            ready = json.loads(ready_line)
        except json.JSONDecodeError as exc:
            proc.kill()
            raise EngineError(
                f"Worker emitted invalid ready line: {ready_line!r} ({exc})"
            ) from exc

        if ready.get("type") != "ready":
            proc.kill()
            raise EngineError(f"Worker failed to boot: {ready}")

        self._proc = proc
        self._actions = {a["action"]: a for a in ready.get("actions", [])}
        self._start_stderr_pump(proc)
        self._bus.emit(
            "worker.ready",
            {"pid": ready.get("pid"), "actions": list(self._actions.keys())},
        )

    def _restricted_env(self) -> dict[str, str]:
        keep = {
            "PATH", "PATHEXT", "PYTHONPATH", "PYTHONHOME", "PYTHONIOENCODING",
            "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "TEMP", "TMP", "COMSPEC",
            "HOME", "USERPROFILE", "USERNAME", "LOGNAME", "LANG", "LC_ALL",
            "AURA_LOG_PATH", "AURA_SHELL_TIMEOUT",
            "AURA_PROTECTED_PATHS", "AURA_SANDBOX_DIR",
            "LOCALAPPDATA", "APPDATA",
        }
        env = {k: v for k, v in os.environ.items() if k.upper() in keep}
        env["AURA_WORKER"] = "1"
        env["PYTHONIOENCODING"] = env.get("PYTHONIOENCODING", "utf-8")
        # Bind the manifest hash so the worker can verify its local copy.
        if self._manifest_hash is None:
            # Lazy compute on first spawn — defends against a caller
            # forgetting to call :meth:`_bind_manifest_for_worker`.
            try:
                self._manifest_hash = manifest_sha256(
                    default_manifest_path(self._root)
                )
            except Exception:
                self._manifest_hash = None
        if self._manifest_hash:
            env["AURA_MANIFEST_SHA256"] = self._manifest_hash
        # Help worker find the repo even without PYTHONPATH propagation.
        root = str(self._root)
        pp = env.get("PYTHONPATH", "")
        if root not in pp.split(os.pathsep):
            env["PYTHONPATH"] = root + (os.pathsep + pp if pp else "")
        return env

    def _start_stderr_pump(self, proc: subprocess.Popen[str]) -> None:
        """Pump worker stderr lines into our logger without blocking."""

        def pump() -> None:
            assert proc.stderr is not None
            for line in proc.stderr:
                line = line.rstrip("\n")
                if not line:
                    continue
                # Worker writes JSON to stderr; re-emit as logger.info.
                self._logger.info(
                    "worker.stderr",
                    extra={"event": "worker.stderr", "line": line},
                )

        t = threading.Thread(target=pump, name="aura-worker-stderr", daemon=True)
        t.start()

    def shutdown(self, *, timeout: float = 3.0) -> None:
        with self._lock:
            proc = self._proc
            self._proc = None
        if proc is None:
            return
        try:
            if proc.stdin and not proc.stdin.closed:
                proc.stdin.write(json.dumps({"type": "shutdown"}) + "\n")
                proc.stdin.flush()
        except Exception:
            pass
        try:
            proc.wait(timeout=timeout)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        self._bus.emit("worker.shutdown", {})

    # ---- dispatcher protocol -------------------------------------------
    def has(self, action: str) -> bool:
        return action in self._actions

    def actions(self) -> list[str]:
        return list(self._actions.keys())

    def action_meta(self) -> list[dict[str, Any]]:
        return list(self._actions.values())

    # ------------------------------------------------------------------
    # Private dispatch — accessible only via the capability handed out
    # by :meth:`_seal`.  Named-mangled to keep bytecode-inspecting
    # callers away from the short name.
    # ------------------------------------------------------------------
    def __dispatch(self, action: str, params: dict[str, Any]) -> CommandResult:
        if not isinstance(action, str) or not action:
            raise EngineError("action must be a non-empty string")
        if not isinstance(params, dict):
            raise EngineError("params must be a dict")
        if action not in self._actions:
            raise EngineError(f"No executor registered for action {action!r}")

        request = {
            "type": "exec",
            "id": f"req_{uuid.uuid4().hex[:12]}",
            "action": action,
            "params": params,
            "trace_id": current_trace_id(),
        }
        reply = self._rpc(request)
        return self._reply_to_result(reply, fallback_action=action)

    # ------------------------------------------------------------------
    # One-shot capability export (consumed by CommandRegistry.__init__).
    # ------------------------------------------------------------------
    def _seal(self) -> Callable[[str, dict[str, Any]], CommandResult]:
        """Hand the dispatch capability to CommandRegistry exactly once."""
        if self.__sealed:
            raise RuntimeError(
                "WorkerClient has already been sealed; dispatch is private."
            )
        self.__sealed = True
        return self.__dispatch  # bound method — captures self

    @property
    def sealed(self) -> bool:
        return self.__sealed

    # ------------------------------------------------------------------
    # Manifest fingerprint (published to the worker at spawn time).
    # ------------------------------------------------------------------
    def _bind_manifest_for_worker(self, manifest_path: Any = None) -> str:
        """Compute the SHA-256 of the manifest and stash it locally.

        The hash is then passed to the worker via the
        ``AURA_MANIFEST_SHA256`` environment variable (see
        :meth:`_restricted_env`).  A worker whose local manifest differs
        refuses to start.
        """
        path = manifest_path or default_manifest_path(self._root)
        self._manifest_hash = manifest_sha256(path)
        return self._manifest_hash

    # ---- internals ------------------------------------------------------
    def _rpc(self, request: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            proc = self._ensure_running_locked()
            assert proc.stdin is not None
            assert proc.stdout is not None

            try:
                proc.stdin.write(json.dumps(request, default=str) + "\n")
                proc.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                self._handle_crash_locked(exc)
                raise EngineError(f"Worker pipe broken on write: {exc}") from exc

            line = self._read_line(proc, self._timeout)
            if line is None:
                self._handle_crash_locked(RuntimeError("timeout"))
                raise EngineError(
                    f"Worker did not respond within {self._timeout}s; respawning."
                )

            try:
                return json.loads(line)
            except json.JSONDecodeError as exc:
                self._handle_crash_locked(exc)
                raise EngineError(f"Worker returned non-JSON: {line!r}") from exc

    def _ensure_running_locked(self) -> subprocess.Popen[str]:
        if self._proc is None or self._proc.poll() is not None:
            self._spawn()
        assert self._proc is not None
        return self._proc

    def _handle_crash_locked(self, reason: Any) -> None:
        proc = self._proc
        self._proc = None
        if proc is not None:
            try:
                proc.kill()
            except Exception:
                pass
        self._bus.emit(
            "worker.crashed",
            {"reason": str(reason)},
        )

    @staticmethod
    def _read_line(
        proc: subprocess.Popen[str], timeout: float
    ) -> str | None:
        """Blocking read with a deadline — portable across POSIX/Windows."""
        assert proc.stdout is not None
        deadline = time.monotonic() + timeout
        holder: dict[str, str | None] = {"line": None}
        done = threading.Event()

        def reader() -> None:
            try:
                holder["line"] = proc.stdout.readline()
            except Exception:
                holder["line"] = None
            finally:
                done.set()

        t = threading.Thread(target=reader, name="aura-worker-read", daemon=True)
        t.start()
        t.join(timeout=max(0.0, deadline - time.monotonic()))
        if not done.is_set():
            return None
        line = holder["line"]
        if line is None or line == "":
            return None
        return line.rstrip("\n")

    @staticmethod
    def _drain_stderr(proc: subprocess.Popen[str], *, limit: int = 4096) -> str:
        if proc.stderr is None:
            return ""
        try:
            data = proc.stderr.read() or ""
            return data[-limit:]
        except Exception:
            return ""

    def _reply_to_result(
        self, reply: dict[str, Any], *, fallback_action: str
    ) -> CommandResult:
        msg_type = reply.get("type")
        if msg_type == "result":
            return CommandResult(
                success=bool(reply.get("success")),
                message=str(reply.get("message", "")),
                data=dict(reply.get("data") or {}),
                command_type=str(reply.get("command_type") or fallback_action),
                error_code=reply.get("error_code"),
            )
        if msg_type == "error":
            error_class = str(reply.get("error_class") or "ExecutionError")
            msg = str(reply.get("message") or "worker error")
            exc_cls = _import_exc_map().get(error_class, ExecutionError)
            raise exc_cls(msg)
        raise EngineError(f"Unknown worker reply type: {msg_type!r}: {reply!r}")
