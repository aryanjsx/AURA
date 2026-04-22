"""
AURA — Permission Levels and Validation.

Every command is tagged with one of four permission levels.  Sources
(``cli``, ``llm``, ``planner``) have a maximum permitted level; if the
command's level exceeds the cap, execution is denied with
:class:`~aura.core.errors.PermissionDenied`.

Defaults
--------
- ``cli``     → up to ``CRITICAL`` (a human explicitly typed it)
- ``llm``     → up to ``MEDIUM``   (untrusted model input)
- ``planner`` → up to ``HIGH``     (human-approved plan)

Source caps are overridable via ``permissions.source_limits`` in config.
"""

from __future__ import annotations

from enum import Enum
from typing import Mapping

from aura.core.config_loader import get as get_config
from aura.core.errors import PermissionDenied


class PermissionLevel(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    @property
    def rank(self) -> int:
        return _RANK[self]

    @classmethod
    def parse(cls, value: "str | PermissionLevel") -> "PermissionLevel":
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise ValueError(f"PermissionLevel must be str or enum, got {type(value).__name__}")
        key = value.strip().upper()
        try:
            return cls[key]
        except KeyError as exc:
            raise ValueError(f"Unknown permission level: {value!r}") from exc


_RANK: dict[PermissionLevel, int] = {
    PermissionLevel.LOW: 0,
    PermissionLevel.MEDIUM: 1,
    PermissionLevel.HIGH: 2,
    PermissionLevel.CRITICAL: 3,
}


_DEFAULT_SOURCE_CAPS: Mapping[str, PermissionLevel] = {
    "cli": PermissionLevel.CRITICAL,
    "llm": PermissionLevel.MEDIUM,
    "planner": PermissionLevel.HIGH,
    "auto": PermissionLevel.LOW,
}


class PermissionValidator:
    """Validates command permission levels against the calling source's cap."""

    def __init__(self, source_caps: Mapping[str, PermissionLevel] | None = None) -> None:
        configured = get_config("permissions.source_limits", {}) or {}
        caps: dict[str, PermissionLevel] = dict(_DEFAULT_SOURCE_CAPS)
        for src, raw in configured.items():
            try:
                caps[str(src).lower()] = PermissionLevel.parse(raw)
            except ValueError:
                continue
        if source_caps:
            for src, level in source_caps.items():
                caps[str(src).lower()] = PermissionLevel.parse(level)
        self._caps: Mapping[str, PermissionLevel] = caps

    def cap_for(self, source: str) -> PermissionLevel:
        return self._caps.get((source or "").lower(), PermissionLevel.LOW)

    def validate(
        self,
        *,
        action: str,
        level: PermissionLevel,
        source: str,
    ) -> None:
        """Raise :class:`PermissionDenied` if *level* exceeds *source* cap."""
        cap = self.cap_for(source)
        if level.rank > cap.rank:
            raise PermissionDenied(
                f"'{action}' requires {level.value}; "
                f"source '{source}' is capped at {cap.value}."
            )
