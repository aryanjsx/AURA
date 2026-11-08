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
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Literal, Optional

Risk = Literal["read", "change", "run"]
Decision = Literal["approve", "approve_tool", "deny"]

#: Tools that only read, or write to Locus's own memory. They never ask.
READ_ONLY_TOOLS = frozenset(
    {
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
        risk = tool_risk(tool_name, self._tools.get(tool_name), arguments)
        if risk == "read" or tool_name in self._allowed_tools:
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
        approved = decision in ("approve", "approve_tool")
        if decision == "approve_tool":
            self._allowed_tools.add(tool_name)
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
