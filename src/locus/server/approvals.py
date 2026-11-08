"""In-chat approvals for Agent mode.

Before the agent runs a tool that changes something, :func:`before_tool_call`
pauses the agent's thread, the chat stream sends an ``approval_required``
event, and the agent waits until the user answers through
``POST /v1/chat/approvals/{id}`` (or the request is stopped).

Each streamed agent run gets an :class:`ApprovalSession`, set in
:data:`current_session` before the run starts on its worker thread. Runs with
no session (non-streaming requests) can't ask, so risky tools are denied.
``POST /v1/chat/runs/{run_id}/stop`` cancels a session's run.
"""

from __future__ import annotations

import contextvars
import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Literal, Optional

Risk = Literal["read", "change", "run"]
# "always" also saves a lasting rule; it applies only to "change" calls.
Decision = Literal["approve", "approve_tool", "always", "deny"]

#: Tools that only read, or write to Locus's own memory. They never ask.
READ_ONLY_TOOLS = frozenset(
    {
        "task_plan",
        "think",
        "calculator",
        "file_read",
        "pdf_extract",
        "memory_manage",
        "memory_search",
        "memory_retrieve",
        "knowledge_search",
        "git_status",
        "git_diff",
        "git_log",
    }
)

#: Tools that run code or commands. Every call asks.
RUN_TOOLS = frozenset(
    {
        "shell_exec",
        "docker_shell_exec",
        "code_interpreter",
        "code_interpreter_docker",
        "repl",
    }
)

#: How long the agent waits for an answer before treating it as a no.
APPROVAL_TIMEOUT_SECONDS = 300.0


def tool_risk(name: str, tool: Any = None, arguments: Optional[dict] = None) -> Risk:
    """Classify a tool call. Unknown tools ask, so new tools fail closed.

    A tool whose risk depends on what it's asked to do (listing windows vs
    closing an app) can define ``risk_for(arguments)``.
    """
    spec = getattr(tool, "spec", None)
    if name in RUN_TOOLS or getattr(spec, "requires_confirmation", False):
        return "run"
    risk_for = getattr(tool, "risk_for", None)
    if callable(risk_for):
        try:
            risk = risk_for(arguments or {})
        except Exception:
            risk = "change"
        return risk if risk in ("read", "change", "run") else "change"
    if name in READ_ONLY_TOOLS:
        return "read"
    return "change"


#: Previews longer than this are cut before they're sent to the chat.
MAX_PREVIEW_CHARS = 8000


def rule_key(tool_name: str, arguments: Optional[dict] = None) -> str:
    """A lasting rule covers one tool, or one action of it (``tool:action``)."""
    action = (arguments or {}).get("action")
    return f"{tool_name}:{action}" if isinstance(action, str) and action else tool_name


class PermissionRules:
    """ "Always allow" rules, kept in ``~/.locus/agent_permissions.json``."""

    def __init__(self, path: Optional[Path] = None) -> None:
        if path is None:
            from locus.core.paths import get_config_dir

            path = Path(get_config_dir()) / "agent_permissions.json"
        self.path = Path(path)
        self._lock = threading.Lock()

    def _load(self) -> Dict[str, dict]:
        try:
            rows = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return {r["key"]: r for r in rows if isinstance(r, dict) and r.get("key")}

    def _save(self, rules: Dict[str, dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(list(rules.values()), indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def allows(self, tool_name: str, arguments: Optional[dict] = None) -> bool:
        with self._lock:
            return rule_key(tool_name, arguments) in self._load()

    def add(self, tool_name: str, arguments: Optional[dict] = None) -> str:
        key = rule_key(tool_name, arguments)
        with self._lock:
            rules = self._load()
            rules[key] = {
                "key": key,
                "tool": tool_name,
                "action": (arguments or {}).get("action"),
                "created": time.time(),
            }
            self._save(rules)
        return key

    def remove(self, key: str) -> bool:
        with self._lock:
            rules = self._load()
            if rules.pop(key, None) is None:
                return False
            self._save(rules)
            return True

    def list(self) -> list:
        with self._lock:
            return sorted(self._load().values(), key=lambda r: r["key"])


_rules: Optional[PermissionRules] = None
_rules_lock = threading.Lock()


def get_rules() -> PermissionRules:
    global _rules
    with _rules_lock:
        if _rules is None:
            _rules = PermissionRules()
        return _rules


class AgentCancelled(BaseException):
    """Raised on the agent's thread to stop a run the user stopped.

    A ``BaseException`` so the orchestrator's ``except Exception`` around the
    tool hook can't turn it into an ordinary denial and keep looping.
    """


@dataclass
class _Pending:
    id: str
    tool: str
    answered: threading.Event = field(default_factory=threading.Event)
    decision: Optional[Decision] = None


_pending: Dict[str, _Pending] = {}
_sessions: Dict[str, "ApprovalSession"] = {}
_pending_lock = threading.Lock()


def resolve(approval_id: str, decision: Decision) -> bool:
    """Answer a pending approval. Returns ``False`` if it isn't waiting."""
    with _pending_lock:
        pending = _pending.get(approval_id)
    if pending is None or pending.answered.is_set():
        return False
    pending.decision = decision
    pending.answered.set()
    return True


def stop_run(run_id: str) -> bool:
    """Stop the run with *run_id*. Returns ``False`` if it isn't running."""
    with _pending_lock:
        session = _sessions.get(run_id)
    if session is None:
        return False
    session.cancel()
    return True


class ApprovalSession:
    """Approvals for one agent run.

    *emit* sends an SSE event (name, data) to this run's chat stream; it must
    be safe to call from the agent's thread.
    """

    def __init__(
        self,
        emit: Callable[[str, dict], None],
        *,
        tools: Optional[Dict[str, Any]] = None,
        timeout: float = APPROVAL_TIMEOUT_SECONDS,
    ) -> None:
        self._emit = emit
        self._tools = tools or {}
        self._timeout = timeout
        self._allowed_tools: set[str] = set()
        self._ids: set[str] = set()
        self.cancelled = threading.Event()
        self.run_id = uuid.uuid4().hex

    def __enter__(self) -> "ApprovalSession":
        with _pending_lock:
            _sessions[self.run_id] = self
        return self

    def __exit__(self, *exc: Any) -> None:
        with _pending_lock:
            _sessions.pop(self.run_id, None)

    def cancel(self) -> None:
        """Stop the run: deny anything waiting and every later tool call."""
        self.cancelled.set()
        with _pending_lock:
            waiting = [_pending[i] for i in self._ids if i in _pending]
        for pending in waiting:
            pending.answered.set()

    def check(self, tool_name: str, arguments: dict) -> bool:
        """Return whether *tool_name* may run, asking the user if needed."""
        if self.cancelled.is_set():
            raise AgentCancelled()
        tool = self._tools.get(tool_name)
        risk = tool_risk(tool_name, tool, arguments)
        if risk == "read" or tool_name in self._allowed_tools:
            return True
        # Lasting rules never cover "run" calls: commands and code always ask.
        if risk == "change" and get_rules().allows(tool_name, arguments):
            return True

        pending = _Pending(id=uuid.uuid4().hex, tool=tool_name)
        with _pending_lock:
            _pending[pending.id] = pending
            self._ids.add(pending.id)
        try:
            self._emit(
                "approval_required",
                {
                    "id": pending.id,
                    "tool": tool_name,
                    "arguments": arguments,
                    "risk": risk,
                    "can_always": risk == "change",
                    "rule": rule_key(tool_name, arguments),
                    "preview": _preview(tool, arguments),
                    "timeout_seconds": self._timeout,
                },
            )
            deadline = time.monotonic() + self._timeout
            while not pending.answered.wait(timeout=0.5):
                if time.monotonic() >= deadline:
                    break
        finally:
            with _pending_lock:
                _pending.pop(pending.id, None)
                self._ids.discard(pending.id)

        if self.cancelled.is_set():
            raise AgentCancelled()
        decision = pending.decision
        approved = decision in ("approve", "approve_tool", "always")
        if decision == "approve_tool":
            self._allowed_tools.add(tool_name)
        elif decision == "always" and risk == "change":
            get_rules().add(tool_name, arguments)
        self._emit(
            "approval_resolved",
            {
                "id": pending.id,
                "tool": tool_name,
                "approved": approved,
                "timed_out": decision is None,
            },
        )
        return approved


def _preview(tool: Any, arguments: dict) -> Optional[str]:
    """What the call would change (a diff, say), if the tool can tell."""
    preview_for = getattr(tool, "preview_for", None)
    if not callable(preview_for):
        return None
    try:
        text = preview_for(arguments)
    except Exception:
        return None
    if not text:
        return None
    text = str(text)
    if len(text) > MAX_PREVIEW_CHARS:
        text = text[:MAX_PREVIEW_CHARS] + "\n… (preview cut off)"
    return text


current_session: contextvars.ContextVar[Optional[ApprovalSession]] = (
    contextvars.ContextVar("locus_approval_session", default=None)
)


def before_tool_call(tool_name: str, arguments: dict) -> bool:
    """Orchestrator hook for the Agent mode agent."""
    session = current_session.get()
    if session is None:
        return tool_risk(tool_name) == "read"
    return session.check(tool_name, arguments)


def confirm_after_approval(prompt: str) -> bool:
    """Executor confirmation for tools marked ``requires_confirmation``.

    :func:`before_tool_call` has already asked the user (it runs first and
    treats these tools as ``run``), so confirm only inside an approval session.
    """
    return current_session.get() is not None
