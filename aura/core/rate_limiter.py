"""
AURA — Rate Limiter and Loop Protection (per-source buckets).

Two guardrails, each kept in an isolated bucket per *source* (``cli``,
``llm``, ``planner`` …) so that a flooding LLM cannot exhaust the CLI's
budget and vice versa:

1. **Sliding window** — at most ``max_per_minute`` commands succeed in
   any 60-second window per source.
2. **Repetition guard** — if the same ``(action, params_signature)``
   tuple is submitted ``repeat_threshold`` times in a row from a single
   source, it is treated as an infinite loop and rejected.

Source-specific overrides may be supplied in config::

    rate_limit:
      max_per_minute: 60
      repeat_threshold: 10
      sources:
        llm:     {max_per_minute: 30, repeat_threshold: 5}
        planner: {max_per_minute: 120, repeat_threshold: 20}

Both limits are configurable via ``rate_limit.*`` in config.
"""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from aura.core.config_loader import get as get_config
from aura.core.errors import RateLimitError


@dataclass
class _Bucket:
    max_per_minute: int
    repeat_threshold: int
    events: deque[float] = field(default_factory=deque)
    recent: deque[str] = field(default_factory=deque)


class RateLimiter:
    """Thread-safe per-source sliding-window rate + repeat guard."""

    WINDOW_SECONDS: float = 60.0

    def __init__(
        self,
        max_per_minute: int | None = None,
        repeat_threshold: int | None = None,
        *,
        source_overrides: dict[str, dict[str, int]] | None = None,
    ) -> None:
        self._default_max = int(
            max_per_minute if max_per_minute is not None
            else get_config("rate_limit.max_per_minute", 60)
        )
        self._default_repeat = int(
            repeat_threshold if repeat_threshold is not None
            else get_config("rate_limit.repeat_threshold", 10)
        )
        if self._default_max <= 0:
            raise ValueError("rate_limit.max_per_minute must be > 0")
        if self._default_repeat <= 1:
            raise ValueError("rate_limit.repeat_threshold must be > 1")

        # If the caller explicitly customised the default limits, respect
        # them verbatim and DO NOT silently re-enable per-source overrides
        # from config (that would surprise tests and library consumers).
        explicit_override = (
            max_per_minute is not None or repeat_threshold is not None
        )
        if source_overrides is not None:
            overrides = source_overrides
        elif explicit_override:
            overrides = {}
        else:
            overrides = get_config("rate_limit.sources", {}) or {}
        self._overrides: dict[str, dict[str, int]] = {}
        if isinstance(overrides, dict):
            for src, cfg in overrides.items():
                if not isinstance(cfg, dict):
                    continue
                self._overrides[str(src)] = {
                    "max_per_minute": int(cfg.get("max_per_minute", self._default_max)),
                    "repeat_threshold": int(cfg.get("repeat_threshold", self._default_repeat)),
                }

        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    # ---- helpers --------------------------------------------------------
    @staticmethod
    def _signature(action: str, params: dict[str, Any]) -> str:
        try:
            frozen = json.dumps(params, sort_keys=True, default=str)
        except Exception:
            frozen = repr(sorted(params.items()))
        return f"{action}::{frozen}"

    def _bucket_locked(self, source: str) -> _Bucket:
        bucket = self._buckets.get(source)
        if bucket is None:
            override = self._overrides.get(source, {})
            bucket = _Bucket(
                max_per_minute=int(
                    override.get("max_per_minute", self._default_max)
                ),
                repeat_threshold=int(
                    override.get("repeat_threshold", self._default_repeat)
                ),
            )
            bucket.recent = deque(maxlen=bucket.repeat_threshold)
            self._buckets[source] = bucket
        return bucket

    # ---- public API -----------------------------------------------------
    def check(
        self,
        action: str,
        params: dict[str, Any],
        *,
        source: str = "cli",
    ) -> None:
        """Raise :class:`RateLimitError` if this command should be blocked."""
        now = time.monotonic()
        signature = self._signature(action, params)
        src = (source or "cli").strip() or "cli"

        with self._lock:
            bucket = self._bucket_locked(src)
            cutoff = now - self.WINDOW_SECONDS
            while bucket.events and bucket.events[0] < cutoff:
                bucket.events.popleft()

            if len(bucket.events) >= bucket.max_per_minute:
                raise RateLimitError(
                    f"Rate limit exceeded for source={src!r}: "
                    f"{bucket.max_per_minute} commands/minute "
                    f"({len(bucket.events)} in last 60s)."
                )

            bucket.recent.append(signature)
            if (
                len(bucket.recent) >= bucket.repeat_threshold
                and all(s == signature for s in bucket.recent)
            ):
                raise RateLimitError(
                    f"Loop protection [{src}]: '{action}' repeated "
                    f"{bucket.repeat_threshold}x with identical params — aborting."
                )

            bucket.events.append(now)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "default_max_per_minute": self._default_max,
                "default_repeat_threshold": self._default_repeat,
                "sources": {
                    src: {
                        "max_per_minute": b.max_per_minute,
                        "repeat_threshold": b.repeat_threshold,
                        "in_flight_window": len(b.events),
                        "recent_signatures": list(b.recent),
                    }
                    for src, b in self._buckets.items()
                },
            }
