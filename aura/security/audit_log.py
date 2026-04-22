"""
AURA — Audit Log (tamper-evident, rotating).

A *separate* JSON-line log dedicated to security-relevant events:

- confirmation lifecycle (requested / accepted / denied / timed out)
- permission denials
- rate-limit rejections
- policy violations (shell denylist, sandbox escape, …)
- every destructive command execution and its outcome
- full command lifecycle (executing / completed)
- plan lifecycle (started / completed / rollback / failed) including
  the full structure of the plan at ``plan.started``
- worker lifecycle (ready / crashed / shutdown)

Tamper evidence
---------------
Every record includes two fields:

* ``prev_hash`` — SHA-256 of the previous record's ``hash`` field.
* ``hash``     — SHA-256 of ``prev_hash`` concatenated with the canonical
  JSON of the record body (all fields except ``hash`` itself).

On startup we load the last record's ``hash`` so the chain continues
across process restarts.  ANY modification of ANY line invalidates every
subsequent ``hash`` — detectable by a single forward pass.

Rotation
--------
Uses :class:`logging.handlers.RotatingFileHandler` so long-running
systems never grow the file without bound.  The hash chain is kept in
memory so it survives rotation transparently.

Verification
------------
See :func:`verify_chain` — given a path, returns ``(ok, first_bad_line)``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import logging.handlers
import threading
import time
from pathlib import Path
from typing import Any

from aura.security.audit_events import AuditEventRegistry, get_audit_event_registry
from aura.core.config_loader import get as get_config
from aura.core.event_bus import EventBus

_GENESIS_HASH = "0" * 64


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _last_hash_in(path: Path) -> str:
    """Scan *path* backwards to find the most recent record's ``hash``.
    Returns the genesis hash if the file is missing / empty / unreadable."""
    if not path.exists():
        return _GENESIS_HASH
    try:
        with path.open("rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            chunk = 4096
            buffer = b""
            while size > 0:
                read_size = min(chunk, size)
                size -= read_size
                fh.seek(size)
                buffer = fh.read(read_size) + buffer
                if b"\n" in buffer.strip(b"\n"):
                    break
            for line in reversed(buffer.splitlines()):
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                except Exception:
                    continue
                h = data.get("hash")
                if isinstance(h, str) and len(h) == 64:
                    return h
    except Exception:
        pass
    return _GENESIS_HASH


class _ChainedAuditFormatter(logging.Formatter):
    """Formatter that emits JSON lines with a SHA-256 hash chain."""

    def __init__(self, initial_hash: str) -> None:
        super().__init__()
        self._prev_hash = initial_hash or _GENESIS_HASH
        self._lock = threading.Lock()

    @property
    def current_hash(self) -> str:
        with self._lock:
            return self._prev_hash

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        # ``RotatingFileHandler.shouldRollover`` calls ``format()`` once
        # just to measure size, then ``emit()`` calls it again to write.
        # We must NOT advance the hash chain twice per record — so we
        # memoise the output on the record itself.
        cached = getattr(record, "_aura_audit_formatted", None)
        if cached is not None:
            return cached

        body: dict[str, Any] = {
            "timestamp": time.strftime(
                "%Y-%m-%dT%H:%M:%S", time.localtime(record.created)
            ) + f".{int(record.msecs):03d}",
            "event": record.__dict__.get("event", record.getMessage()),
        }
        payload = record.__dict__.get("data")
        if isinstance(payload, dict):
            body["payload"] = payload
        else:
            body["payload"] = {}

        with self._lock:
            body["prev_hash"] = self._prev_hash
            canonical = _canonical(body)
            new_hash = _sha256(self._prev_hash + canonical)
            body["hash"] = new_hash
            self._prev_hash = new_hash

        try:
            output = json.dumps(body, ensure_ascii=False, default=str)
        except Exception:
            output = json.dumps(
                {"event": body.get("event"), "error": "serialize_failed",
                 "prev_hash": body.get("prev_hash"), "hash": body.get("hash")}
            )
        record._aura_audit_formatted = output  # type: ignore[attr-defined]
        return output


class AuditLogger:
    """Subscribes to security events on the bus and writes them to disk."""

    _SUBSCRIBED_FLAG = "_aura_audit_subscribed"

    def __init__(
        self,
        bus: EventBus,
        path: str | Path | None = None,
        *,
        max_bytes: int | None = None,
        backup_count: int | None = None,
        event_registry: AuditEventRegistry | None = None,
    ) -> None:
        self._bus = bus
        self._event_registry = event_registry or get_audit_event_registry()
        target = Path(path) if path else Path(
            get_config("audit.file", "logs/audit.log")
        ).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)

        self._max_bytes = int(
            max_bytes if max_bytes is not None
            else get_config("audit.max_bytes", 5 * 1024 * 1024)
        )
        self._backup_count = int(
            backup_count if backup_count is not None
            else get_config("audit.backup_count", 5)
        )

        self._logger = logging.getLogger("aura.audit")
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False

        # Remove any stale audit handler from a prior instance (tests,
        # re-bootstraps, etc.) so we always write to *this* path and
        # continue *this* chain.
        for old in list(self._logger.handlers):
            if getattr(old, "_aura_audit", False):
                try:
                    old.close()
                except Exception:
                    pass
                self._logger.removeHandler(old)

        initial_hash = _last_hash_in(target)
        handler = logging.handlers.RotatingFileHandler(
            target,
            maxBytes=self._max_bytes,
            backupCount=self._backup_count,
            encoding="utf-8",
        )
        self._formatter = _ChainedAuditFormatter(initial_hash)
        handler.setFormatter(self._formatter)
        handler._aura_audit = True  # type: ignore[attr-defined]
        self._logger.addHandler(handler)

        self._tokens: list[str] = []
        self._path = target

    @property
    def path(self) -> Path:
        return self._path

    def current_hash(self) -> str | None:
        fm = self._formatter
        return fm.current_hash if isinstance(fm, _ChainedAuditFormatter) else None

    def subscribe(self) -> None:
        """Subscribe to every currently-registered audit event.

        Safe to call multiple times: events newly registered between
        calls will get subscribers added on the next call, so plugins
        loaded after boot still get coverage if `subscribe()` is
        re-invoked after `PluginLoader.load_all()`.
        """
        if not getattr(self._bus, self._SUBSCRIBED_FLAG, False):
            setattr(self._bus, self._SUBSCRIBED_FLAG, set())
        already: set[str] = getattr(self._bus, self._SUBSCRIBED_FLAG)
        for event in self._event_registry.events():
            if event in already:
                continue
            token = self._bus.subscribe(event, self._handle)
            self._tokens.append(token)
            already.add(event)

    def unsubscribe(self) -> None:
        for token in self._tokens:
            self._bus.unsubscribe(token)
        self._tokens.clear()

    def _handle(self, envelope: dict[str, Any]) -> None:
        event_name = envelope.get("event") or "audit"
        self._logger.info(
            event_name,
            extra={"event": event_name, "data": envelope.get("payload", {})},
        )


# ---------------------------------------------------------------------------
# Stand-alone chain verifier
# ---------------------------------------------------------------------------
def _verify_stream(
    lines: Any, starting_prev: str
) -> tuple[bool, int | None, str]:
    """Walk *lines* (iterable of raw lines), return ``(ok, bad_idx, last_hash)``."""
    prev = starting_prev
    for idx, raw in enumerate(lines, start=1):
        line = raw.rstrip("\n")
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            return False, idx, prev
        stored_hash = record.get("hash")
        prev_hash = record.get("prev_hash")
        if stored_hash is None or prev_hash is None:
            return False, idx, prev
        if prev_hash != prev:
            return False, idx, prev
        body = {k: v for k, v in record.items() if k != "hash"}
        canonical = _canonical(body)
        expected = _sha256(prev + canonical)
        if expected != stored_hash:
            return False, idx, prev
        prev = stored_hash
    return True, None, prev


def verify_chain(path: str | Path) -> tuple[bool, int | None]:
    """Verify the hash chain of a single audit-log file.

    Returns
    -------
    (ok, first_bad_line) :
        * ``(True, None)``  — every record verifies.
        * ``(False, N)``    — line *N* (1-indexed) failed verification.
    """
    p = Path(path)
    if not p.exists():
        return True, None  # empty chain trivially consistent

    with p.open("r", encoding="utf-8") as fh:
        ok, bad, _ = _verify_stream(fh, _GENESIS_HASH)
    return ok, bad


def verify_chain_dir(
    base_path: str | Path,
) -> tuple[bool, str | None, int | None]:
    """Verify the full hash chain **across** rotated log files.

    ``RotatingFileHandler`` names rotated segments ``base.N`` where ``N``
    increases with *age*: ``base.1`` is the most recent rotated file,
    ``base.2`` is older, etc.  The live file is simply ``base``.

    The chain therefore runs oldest→newest:

        base.N, base.N-1, …, base.2, base.1, base

    Returns
    -------
    (ok, filename, bad_line) :
        * ``(True, None, None)``  — every rotated segment + the live
          file verify, and every segment's first record links to the
          previous segment's last record.
        * ``(False, "audit.log.3", 42)`` — file *audit.log.3* had its
          line *42* break the chain.
    """
    base = Path(base_path)
    parent = base.parent

    # Collect all existing rotated segments by suffix number.  Unknown
    # suffixes / foreign files are ignored so dropping an attacker-
    # planted file next to the log cannot DoS verification.
    segments: list[tuple[int, Path]] = []
    prefix = base.name + "."
    if parent.exists():
        for entry in parent.iterdir():
            if not entry.is_file():
                continue
            if entry.name == base.name:
                continue
            if not entry.name.startswith(prefix):
                continue
            suffix = entry.name[len(prefix):]
            if not suffix.isdigit():
                continue
            segments.append((int(suffix), entry))

    # Rotated files walked from oldest to newest (largest N first).
    segments.sort(key=lambda pair: pair[0], reverse=True)
    ordered_paths: list[Path] = [p for _, p in segments]
    if base.exists():
        ordered_paths.append(base)

    prev = _GENESIS_HASH
    for path in ordered_paths:
        with path.open("r", encoding="utf-8") as fh:
            ok, bad, prev = _verify_stream(fh, prev)
        if not ok:
            return False, path.name, bad
    return True, None, None
