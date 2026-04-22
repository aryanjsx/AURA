"""Tests for :mod:`aura.core.logger`."""
from __future__ import annotations

import io
import json
import logging
import time

import pytest

from aura.core import config_loader
from aura.core.logger import JSONFormatter, benchmark, log_event, trace
from aura.core.tracing import TraceScope


def _new_json_logger(name: str, level: int = logging.INFO) -> tuple[logging.Logger, io.StringIO]:
    lg = logging.getLogger(name)
    lg.handlers.clear()
    lg.propagate = False
    buf = io.StringIO()
    h = logging.StreamHandler(buf)
    h.setFormatter(JSONFormatter())
    lg.addHandler(h)
    lg.setLevel(level)
    return lg, buf


def _read_records(buf: io.StringIO) -> list[dict]:
    records: list[dict] = []
    for line in buf.getvalue().splitlines():
        line = line.strip()
        if not line:
            continue
        records.append(json.loads(line))
    return records


def test_json_formatter_emits_required_fields() -> None:
    fmt = JSONFormatter()
    record = logging.LogRecord(
        "t", logging.INFO, __file__, 0, "hello", None, None
    )
    payload = json.loads(fmt.format(record))
    for key in ("timestamp", "level", "logger", "message"):
        assert key in payload
    assert payload["level"] == "INFO"
    assert payload["message"] == "hello"


def test_json_formatter_omits_stdlib_record_fields() -> None:
    fmt = JSONFormatter()
    record = logging.LogRecord(
        "t", logging.INFO, __file__, 0, "x", None, None
    )
    payload = json.loads(fmt.format(record))
    # Must never leak these noisy internals.
    for leaked in ("args", "pathname", "funcName", "relativeCreated", "processName"):
        assert leaked not in payload


def test_json_formatter_inlines_custom_extra_fields() -> None:
    lg, buf = _new_json_logger("aura.test-logger.extras")
    lg.info("demo", extra={"event": "unit.test", "action": "cpu"})
    [rec] = _read_records(buf)
    assert rec["event"] == "unit.test"
    assert rec["action"] == "cpu"


def test_trace_id_present_when_scope_active() -> None:
    lg, buf = _new_json_logger("aura.test-logger.trace")
    with TraceScope() as sc:
        lg.info("inside")
    [rec] = _read_records(buf)
    assert rec["trace_id"] == sc.trace_id


def test_trace_id_absent_outside_scope() -> None:
    lg, buf = _new_json_logger("aura.test-logger.no-trace")
    lg.info("outside")
    [rec] = _read_records(buf)
    assert "trace_id" not in rec


def test_log_event_includes_action_and_latency() -> None:
    lg, buf = _new_json_logger("aura.test-logger.log-event")
    log_event(lg, "manual.event", action="system.cpu", latency_ms=12.3456)
    [rec] = _read_records(buf)
    assert rec["event"] == "manual.event"
    assert rec["action"] == "system.cpu"
    assert rec["latency_ms"] == pytest.approx(12.346)


def test_benchmark_emits_latency_when_enabled() -> None:
    cfg = config_loader.load_config()
    prev = cfg.setdefault("logging", {}).get("benchmark", False)
    cfg["logging"]["benchmark"] = True
    try:
        lg, buf = _new_json_logger("aura.test-logger.bench")
        with benchmark(lg, "unit.benchmark", action="noop"):
            time.sleep(0.02)
        records = _read_records(buf)
        assert records, "benchmark produced no record while enabled"
        [rec] = records
        assert rec["event"] == "unit.benchmark"
        assert rec["latency_ms"] >= 15.0
        # `success` is inside `data` because log_event groups stray
        # kwargs under that key.
        assert rec["data"]["success"] is True
    finally:
        cfg["logging"]["benchmark"] = prev


def test_benchmark_silent_when_disabled() -> None:
    cfg = config_loader.load_config()
    prev_b = cfg.setdefault("logging", {}).get("benchmark", False)
    prev_t = cfg["logging"].get("trace", False)
    cfg["logging"]["benchmark"] = False
    cfg["logging"]["trace"] = False
    try:
        lg, buf = _new_json_logger("aura.test-logger.bench-off")
        with benchmark(lg, "silent.benchmark"):
            pass
        assert _read_records(buf) == []
    finally:
        cfg["logging"]["benchmark"] = prev_b
        cfg["logging"]["trace"] = prev_t


def test_trace_helper_emits_at_trace_level() -> None:
    lg, buf = _new_json_logger("aura.test-logger.trace-helper", level=5)
    trace(lg, "pipeline.step", step="x")
    [rec] = _read_records(buf)
    assert rec["event"] == "pipeline.step"
    assert rec["level"] == "TRACE"
