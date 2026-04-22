"""
AURA — Safety Gate (non-blocking).

Blocks execution of a command until a human confirms.  The confirmation
prompt accepts ONLY the tokens ``yes``, ``confirm``, or ``proceed``
(case-insensitive, stripped).  Any other input — or silence for longer
than :attr:`TIMEOUT_SECONDS` — cancels the command.

Non-blocking implementation
---------------------------
Previous versions spawned a background thread to call :func:`input` and
relied on :class:`queue.Queue.get` with a timeout.  If the user did not
respond, the reader thread survived past the timeout and could *steal*
the next line of real user input — a reliability bug.

We now use OS-level stdin polling:

* POSIX: :func:`select.select`.
* Windows: :mod:`msvcrt` (``kbhit`` / ``getwche``).

Both paths return ``None`` on timeout without leaving any background
thread alive.  A custom ``input_fn`` (used only by tests) falls back to
the legacy threaded path, but the thread is still daemon and a new one
is created per request.
"""

from __future__ import annotations

import sys
import threading
import time
from typing import Callable

from aura.core.config_loader import get as get_config
from aura.core.errors import ConfirmationDenied, ConfirmationTimeout
from aura.core.event_bus import EventBus
from aura.core.logger import get_logger
from aura.core.tracing import current_trace_id

_logger = get_logger("aura.safety_gate")

_POLL_INTERVAL = 0.05  # seconds — Windows kbhit loop resolution


def _read_line_non_blocking(prompt: str, timeout: float) -> str | None:
    """Write *prompt* and read one line from stdin, returning ``None``
    if nothing arrived within *timeout* seconds.  Portable (no orphan
    threads)."""
    sys.stdout.write(prompt)
    try:
        sys.stdout.flush()
    except Exception:
        pass

    if sys.platform == "win32":
        return _win_read_line(timeout)
    return _posix_read_line(timeout)


def _posix_read_line(timeout: float) -> str | None:
    import select  # stdlib — no-op on Windows

    try:
        ready, _, _ = select.select([sys.stdin], [], [], timeout)
    except (OSError, ValueError):
        return None
    if not ready:
        return None
    try:
        return sys.stdin.readline().rstrip("\n")
    except Exception:
        return None


def _win_read_line(timeout: float) -> str | None:
    try:
        import msvcrt  # type: ignore[import-not-found]
    except ImportError:
        return None

    deadline = time.monotonic() + timeout
    buf: list[str] = []
    while time.monotonic() < deadline:
        if msvcrt.kbhit():
            ch = msvcrt.getwche()
            if ch in ("\r", "\n"):
                try:
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                except Exception:
                    pass
                return "".join(buf)
            if ch == "\x08":  # backspace
                if buf:
                    buf.pop()
                continue
            if ch == "\x03":  # Ctrl-C
                raise KeyboardInterrupt
            buf.append(ch)
        else:
            time.sleep(_POLL_INTERVAL)
    return None


class SafetyGate:
    """Interactive confirmation with a hard timeout — no orphan threads."""

    ACCEPTED_RESPONSES: frozenset[str] = frozenset({"yes", "confirm", "proceed"})
    TIMEOUT_SECONDS: float = 8.0

    def __init__(
        self,
        bus: EventBus,
        *,
        input_fn: Callable[[str], str] | None = None,
        output_fn: Callable[[str], None] | None = None,
        timeout: float | None = None,
    ) -> None:
        self._bus = bus
        self._input_fn = input_fn  # None → use OS-level non-blocking read
        self._output_fn = output_fn or print
        configured = timeout
        if configured is None:
            configured = float(
                get_config("safety.confirm_timeout", self.TIMEOUT_SECONDS)
            )
        self._timeout = max(1.0, configured)

    def request(
        self,
        *,
        action: str,
        params: dict,
        source: str,
        permission: str,
        trace_id: str | None = None,
    ) -> None:
        """Block until the user confirms or the gate cancels."""
        trace_id = trace_id or current_trace_id()
        self._bus.emit(
            "confirmation.requested",
            {
                "action": action,
                "source": source,
                "permission": permission,
                "trace_id": trace_id,
                "timeout_seconds": self._timeout,
            },
        )

        prompt = (
            f"\n[AURA-SAFETY] '{action}' ({permission}) — "
            f"respond 'yes' / 'confirm' / 'proceed' within {self._timeout:.0f}s "
            f"to execute.  Anything else cancels.\n> "
        )

        raw = self._read_line(prompt)

        if raw is None:
            self._bus.emit(
                "confirmation.timeout",
                {"action": action, "source": source, "trace_id": trace_id},
            )
            _logger.warning(
                "CONFIRMATION_TIMEOUT",
                extra={
                    "event": "confirmation.timeout",
                    "action": action,
                    "data": {"source": source, "trace_id": trace_id},
                },
            )
            raise ConfirmationTimeout(
                f"No confirmation for '{action}' within {self._timeout:.0f}s — cancelled."
            )

        response = raw.strip().lower()
        if response in self.ACCEPTED_RESPONSES:
            self._bus.emit(
                "confirmation.accepted",
                {"action": action, "source": source, "trace_id": trace_id,
                 "response": response},
            )
            return

        self._bus.emit(
            "confirmation.denied",
            {"action": action, "source": source, "trace_id": trace_id,
             "response": response},
        )
        raise ConfirmationDenied(
            f"Confirmation refused for '{action}' (received {response!r})."
        )

    # ------------------------------------------------------------------
    def _read_line(self, prompt: str) -> str | None:
        """Dispatch to the non-blocking OS reader unless a custom
        ``input_fn`` was supplied (tests only)."""
        if self._input_fn is None:
            return _read_line_non_blocking(prompt, self._timeout)

        # Legacy threaded fallback (custom input_fn, e.g. tests).
        holder: list[str | None] = [None]
        done = threading.Event()

        def worker() -> None:
            try:
                holder[0] = self._input_fn(prompt)  # type: ignore[misc]
            except Exception:
                holder[0] = None
            finally:
                done.set()

        t = threading.Thread(target=worker, daemon=True, name="aura-safety-fallback")
        t.start()
        done.wait(timeout=self._timeout)
        if not done.is_set():
            return None
        return holder[0]


class AutoConfirmGate(SafetyGate):
    """Silent gate that approves every request (tests / ``--yes`` only)."""

    def request(self, **kwargs) -> None:  # type: ignore[override]
        return None
