"""Rate limiter: per-source buckets must not bleed into each other."""
from __future__ import annotations

import pytest

from aura.core.errors import RateLimitError
from aura.core.rate_limiter import RateLimiter


def test_sources_have_independent_quotas() -> None:
    rl = RateLimiter(
        max_per_minute=2,
        repeat_threshold=100,
        source_overrides={},
    )
    rl.check("x", {"a": 1}, source="cli")
    rl.check("x", {"a": 2}, source="cli")
    with pytest.raises(RateLimitError):
        rl.check("x", {"a": 3}, source="cli")

    # LLM bucket is untouched.
    rl.check("x", {"a": 1}, source="llm")
    rl.check("x", {"a": 2}, source="llm")
    with pytest.raises(RateLimitError):
        rl.check("x", {"a": 3}, source="llm")


def test_per_source_override_honored() -> None:
    rl = RateLimiter(
        max_per_minute=5,
        repeat_threshold=100,
        source_overrides={
            "llm": {"max_per_minute": 1, "repeat_threshold": 100},
        },
    )
    # LLM is throttled at 1/minute…
    rl.check("x", {}, source="llm")
    with pytest.raises(RateLimitError):
        rl.check("x", {}, source="llm")
    # …but CLI still has 5.
    for _ in range(5):
        rl.check("x", {}, source="cli")


def test_repetition_guard_is_per_source() -> None:
    rl = RateLimiter(
        max_per_minute=1000,
        repeat_threshold=3,
        source_overrides={},
    )
    rl.check("a", {}, source="cli")
    rl.check("a", {}, source="cli")
    with pytest.raises(RateLimitError):
        rl.check("a", {}, source="cli")

    # LLM can still call it three more times before its own guard triggers.
    rl.check("a", {}, source="llm")
    rl.check("a", {}, source="llm")
    with pytest.raises(RateLimitError):
        rl.check("a", {}, source="llm")
