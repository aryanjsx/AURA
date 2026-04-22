"""
AURA — Structured Logger.

Features
--------
- JSON-line output (one event per line) with timestamp, level, logger,
  event, action, and latency fields.
- ``TRACE`` level (below DEBUG) for pipeline step inspection.
- :func:`benchmark` context manager — emits a single structured event
  with ``latency_ms`` on exit.
- :func:`trace` helper — one-line pipeline step logger.
- :func:`attach_event_bus_logger` — subscribes to every bus event and
  logs it as a structured record.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Iterator

from aura.core.config_loader import get as get_config
from aura.core.event_bus import EventBus
from aura.core.tracing import current_trace_id

TRACE = 5
logging.addLevelName(TRACE, "TRACE")

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

_LEVEL_MAP: dict[str, int] = {
    "TRACE": TRACE,
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}

_STD_RECORD_FIELDS: frozenset[str] = frozenset({
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "asctime", "taskName",
})


class JSONFormatter(logging.Formatter):
    """Render a :class:`logging.LogRecord` as a compact JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": time.strftime(
                "%Y-%m-%dT%H:%M:%S", time.localtime(record.created)
            ) + f".{int(record.msecs):03d}",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        trace_id = current_trace_id()
        if trace_id is not None and "trace_id" not in record.__dict__:
            payload["trace_id"] = trace_id
        for key, value in record.__dict__.items():
            if key in _STD_RECORD_FIELDS:
                continue
            if key.startswith("_"):
                continue
            payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


_configured: set[str] = set()
_config_lock = threading.Lock()


def _ensure_log_dir(log_file: Path) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)


def get_logger(name: str = "aura") -> logging.Logger:
    """Return a JSON-formatted logger with rotating file + console handlers."""
    logger = logging.getLogger(name)

    with _config_lock:
        if name in _configured:
            return logger

        log_rel = get_config("logging.file", "logs/aura.log")
        log_file = Path(log_rel)
        if not log_file.is_absolute():
            log_file = _PROJECT_ROOT / log_file
        level_name = str(get_config("logging.level", "INFO")).upper()
        level = _LEVEL_MAP.get(level_name, logging.INFO)
        max_bytes = int(get_config("logging.max_bytes", 5_242_880))
        backup_count = int(get_config("logging.backup_count", 3))
        trace_mode = bool(get_config("logging.trace", False))

        effective = TRACE if trace_mode else level
        logger.setLevel(effective)

        _ensure_log_dir(log_file)

        formatter: logging.Formatter
        if str(get_config("logging.format", "json")).lower() == "json":
            formatter = JSONFormatter()
        else:
            formatter = logging.Formatter(
                "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(effective)
        file_handler.setFormatter(formatter)

        console_handler = logging.StreamHandler()
        console_handler.setLevel(max(effective, logging.WARNING))
        console_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        logger.propagate = False

        _configured.add(name)

    return logger


def log_event(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    action: str | None = None,
    latency_ms: float | None = None,
    **extra: Any,
) -> None:
    """Emit a structured event record."""
    data: dict[str, Any] = {"event": event}
    if action is not None:
        data["action"] = action
    if latency_ms is not None:
        data["latency_ms"] = round(float(latency_ms), 3)
    if extra:
        data["data"] = extra
    logger.log(level, event, extra=data)


def trace(logger: logging.Logger, event: str, **extra: Any) -> None:
    """Emit a TRACE-level pipeline step event."""
    log_event(logger, event, level=TRACE, **extra)


@contextmanager
def benchmark(
    logger: logging.Logger,
    event: str,
    *,
    action: str | None = None,
    **extra: Any,
) -> Iterator[dict[str, Any]]:
    """Log *event* with the measured ``latency_ms`` when the block exits."""
    enabled = bool(get_config("logging.benchmark", False)) or bool(
        get_config("logging.trace", False)
    )
    start = time.perf_counter()
    state: dict[str, Any] = {"success": True}
    try:
        yield state
    except Exception:
        state["success"] = False
        raise
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        if enabled:
            log_event(
                logger,
                event,
                level=logging.INFO,
                action=action,
                latency_ms=elapsed_ms,
                success=state.get("success", True),
                **extra,
            )


def attach_event_bus_logger(bus: EventBus, logger: logging.Logger) -> str:
    """Forward every bus event into the structured logger (wildcard subscription)."""
    def _forward(envelope: dict[str, Any]) -> None:
        event = envelope.get("event", "bus.event")
        payload = envelope.get("payload", {}) or {}
        log_event(
            logger,
            event,
            level=logging.DEBUG,
            action=payload.get("action") if isinstance(payload, dict) else None,
            **{"payload": payload},
        )

    return bus.subscribe(EventBus.WILDCARD, _forward)
