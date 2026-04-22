"""
AURA — Trace ID propagation.

Every command entering the router is assigned a short ``trace_id``.
It flows through router → registry → engine → bus events → logs via a
:class:`contextvars.ContextVar`, so every structured log record emitted
while the command is in flight carries the same id.
"""

from __future__ import annotations

import contextvars
import uuid

_trace_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "aura_trace_id", default=None,
)


def new_trace_id() -> str:
    """Return a short (12-hex-char) trace identifier."""
    return uuid.uuid4().hex[:12]


def current_trace_id() -> str | None:
    """Return the trace id bound to this execution context, if any."""
    return _trace_var.get()


def set_trace_id(trace_id: str) -> contextvars.Token[str | None]:
    """Bind *trace_id* to the current context; return a token for reset."""
    return _trace_var.set(trace_id)


def reset_trace_id(token: contextvars.Token[str | None]) -> None:
    _trace_var.reset(token)


class TraceScope:
    """Context manager that enters a fresh trace scope."""

    def __init__(self, trace_id: str | None = None) -> None:
        self._trace_id = trace_id or new_trace_id()
        self._token: contextvars.Token[str | None] | None = None

    @property
    def trace_id(self) -> str:
        return self._trace_id

    def __enter__(self) -> "TraceScope":
        self._token = set_trace_id(self._trace_id)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._token is not None:
            reset_trace_id(self._token)
            self._token = None
