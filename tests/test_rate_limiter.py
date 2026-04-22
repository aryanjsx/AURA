"""RateLimiter tests — sliding window + repeat detection."""
from __future__ import annotations

import pytest

from aura.core.errors import RateLimitError
from aura.core.rate_limiter import RateLimiter


def test_sliding_window_blocks_after_cap():
    rl = RateLimiter(max_per_minute=5, repeat_threshold=100)
    for i in range(5):
        rl.check("cpu", {"i": i})
    with pytest.raises(RateLimitError):
        rl.check("cpu", {"i": 99})


def test_repeat_threshold_blocks_same_command():
    rl = RateLimiter(max_per_minute=1000, repeat_threshold=3)
    rl.check("x", {"a": 1})
    rl.check("x", {"a": 1})
    with pytest.raises(RateLimitError):
        rl.check("x", {"a": 1})


def test_repeat_threshold_ignores_distinct_commands():
    rl = RateLimiter(max_per_minute=1000, repeat_threshold=3)
    rl.check("x", {"a": 1})
    rl.check("y", {"a": 1})
    rl.check("x", {"a": 2})  # different params, no loop
    rl.check("x", {"a": 1})


def test_invalid_configuration_rejected():
    with pytest.raises(ValueError):
        RateLimiter(max_per_minute=0)
    with pytest.raises(ValueError):
        RateLimiter(repeat_threshold=1)
