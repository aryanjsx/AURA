"""Tests for :mod:`aura.core.event_bus`."""
from __future__ import annotations

import threading

import pytest

from aura.core.event_bus import EventBus


def test_multiple_subscribers_fire_in_registration_order() -> None:
    bus = EventBus()
    seen: list[str] = []
    bus.subscribe("x", lambda e: seen.append("a"))
    bus.subscribe("x", lambda e: seen.append("b"))
    bus.subscribe("x", lambda e: seen.append("c"))
    bus.emit("x", {"n": 1})
    assert seen == ["a", "b", "c"]


def test_wildcard_receives_every_event() -> None:
    bus = EventBus()
    received: list[str] = []
    bus.subscribe("*", lambda e: received.append(e["event"]))
    bus.emit("a.1", {})
    bus.emit("b.2", {"k": "v"})
    bus.emit("c.3", None)
    assert received == ["a.1", "b.2", "c.3"]


def test_emit_with_zero_subscribers_does_not_raise() -> None:
    bus = EventBus()
    # No subscribers registered.
    bus.emit("nobody.listening", {"x": 1})  # must be a no-op, not raise.


def test_subscriber_exception_does_not_block_others_and_reemits_error() -> None:
    bus = EventBus()
    errors: list[dict] = []
    good: list[dict] = []

    def boom(_e: dict) -> None:
        raise RuntimeError("boom")

    bus.subscribe("bus.subscriber_error", lambda e: errors.append(e["payload"]))
    bus.subscribe("t", boom)
    bus.subscribe("t", lambda e: good.append(e["payload"]))

    bus.emit("t", {"k": "v"})

    assert good, "good subscriber must still fire"
    assert errors, "failure must be re-emitted on bus.subscriber_error"
    assert errors[0].get("origin_event") == "t"
    assert errors[0].get("error_type") == "RuntimeError"


def test_nested_emit_does_not_deadlock() -> None:
    bus = EventBus()
    depth = {"current": 0, "max": 0}

    def handler(envelope: dict) -> None:
        depth["current"] += 1
        depth["max"] = max(depth["max"], depth["current"])
        if depth["current"] < 4:
            bus.emit("nest", {"depth": depth["current"]})
        depth["current"] -= 1

    bus.subscribe("nest", handler)
    bus.emit("nest", {"depth": 0})
    assert depth["max"] == 4


def test_recursive_subscriber_error_does_not_infinite_loop() -> None:
    bus = EventBus()

    def always_raises(_e: dict) -> None:
        raise ValueError("self-recursive error")

    # If the error channel itself has a throwing subscriber the bus must
    # suppress — otherwise emit() would infinite-recurse.
    bus.subscribe("bus.subscriber_error", always_raises)
    bus.subscribe("t", always_raises)

    bus.emit("t", {})  # must terminate.


def test_thread_safety_under_concurrent_emit() -> None:
    bus = EventBus()
    counter = {"n": 0}
    lock = threading.Lock()

    def sub(_e: dict) -> None:
        with lock:
            counter["n"] += 1

    bus.subscribe("c", sub)

    def emitter() -> None:
        for _ in range(500):
            bus.emit("c", {"x": 1})

    threads = [threading.Thread(target=emitter) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert counter["n"] == 8 * 500


def test_unsubscribe_removes_only_that_handler() -> None:
    bus = EventBus()
    a: list[int] = []
    b: list[int] = []
    tok_a = bus.subscribe("e", lambda _: a.append(1))
    bus.subscribe("e", lambda _: b.append(1))

    assert bus.unsubscribe(tok_a) is True
    bus.emit("e", {})
    assert a == []
    assert b == [1]


def test_invalid_event_type_or_handler_rejected() -> None:
    bus = EventBus()
    with pytest.raises(ValueError):
        bus.subscribe("", lambda _: None)
    with pytest.raises(TypeError):
        bus.subscribe("x", "not-a-callable")  # type: ignore[arg-type]
