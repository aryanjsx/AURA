"""
AURA — Configuration Loader

Loads settings from ``config.yaml`` (user-local, gitignored) with
fallback to ``config.example.yaml`` (tracked template).  If neither
file exists or PyYAML is not installed, built-in defaults are used so
that every module has a guaranteed baseline.

Environment variables (optional overrides after YAML merge):

- ``AURA_LOG_PATH`` — overrides ``logging.file``
- ``AURA_SHELL_TIMEOUT`` — overrides ``shell.timeout`` (integer seconds)
- ``AURA_PROTECTED_PATHS`` — comma-separated list overriding ``paths.protected``

Usage::

    from core.config_loader import get as get_config

    level = get_config("logging.level")            # -> "INFO"
    tools = get_config("system_check.tools")        # -> ["python", ...]
    missing = get_config("no.such.key", "fallback") # -> "fallback"
"""

from __future__ import annotations

import copy
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("aura.config")

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

_CONFIG_PATH = _PROJECT_ROOT / "config.yaml"
_FALLBACK_PATH = _PROJECT_ROOT / "config.example.yaml"

_DEFAULTS: dict[str, Any] = {
    "aura": {
        "name": "AURA",
        "version": "0.1.0",
        "mode": "offline",
    },
    "paths": {
        "protected": [
            "C:/Windows",
            "C:/Windows/System32",
            "C:/Program Files",
            "C:/Program Files (x86)",
            "/bin",
            "/usr",
            "/etc",
            "/sbin",
            "/boot",
        ],
    },
    "project_scaffold": {
        "folders": ["src", "tests", "docs", "logs"],
        "files": ["README.md", ".gitignore"],
    },
    "logging": {
        "file": "logs/aura.log",
        "level": "INFO",
        "max_bytes": 5_242_880,
        "backup_count": 3,
    },
    "system_check": {
        "tools": ["python", "git", "node", "docker"],
    },
    "shell": {
        "timeout": 120,
    },
    "llm": {
        "mode": "offline",
        "provider": "ollama",
        "model": "llama3",
        "host": "http://localhost:11434",
    },
}

_cache: dict[str, Any] | None = None


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge *override* into a copy of *base*."""
    merged = base.copy()
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _apply_env_overrides(cfg: dict[str, Any]) -> dict[str, Any]:
    """Apply ``AURA_*`` environment variable overrides to *cfg*."""
    merged = copy.deepcopy(cfg)

    log_path = os.environ.get("AURA_LOG_PATH")
    if log_path and log_path.strip():
        merged.setdefault("logging", {})["file"] = log_path.strip()

    timeout_raw = os.environ.get("AURA_SHELL_TIMEOUT")
    if timeout_raw and timeout_raw.strip():
        try:
            merged.setdefault("shell", {})["timeout"] = int(timeout_raw.strip())
        except ValueError:
            logger.warning(
                "Invalid AURA_SHELL_TIMEOUT ignored (expected integer): %s",
                timeout_raw,
            )

    protected_raw = os.environ.get("AURA_PROTECTED_PATHS")
    if protected_raw and protected_raw.strip():
        paths = [p.strip() for p in protected_raw.split(",") if p.strip()]
        if paths:
            merged.setdefault("paths", {})["protected"] = paths

    return merged


def load_config() -> dict[str, Any]:
    """Load and cache the merged configuration dictionary."""
    global _cache
    if _cache is not None:
        return _cache

    raw: dict[str, Any] = {}
    path = _CONFIG_PATH if _CONFIG_PATH.exists() else _FALLBACK_PATH

    if path.exists():
        try:
            import yaml  # noqa: PLC0415 — deferred so missing PyYAML is non-fatal

            with path.open("r", encoding="utf-8") as fh:
                raw = yaml.safe_load(fh) or {}
        except ImportError:
            logger.warning(
                "PyYAML not installed — using built-in defaults only.",
            )
        except Exception as exc:
            logger.warning("Failed to parse %s: %s", path.name, exc)

    merged = _deep_merge(_DEFAULTS, raw)
    _cache = _apply_env_overrides(merged)
    return _cache


def get(key: str, default: Any = None) -> Any:
    """Retrieve a config value using dot-separated keys.

    Examples::

        get("logging.level")        # -> "INFO"
        get("paths.protected")      # -> [...]
        get("missing.key", 42)      # -> 42
    """
    config = load_config()
    current: Any = config
    for part in key.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return default
        if current is None:
            return default
    return current


def reload() -> dict[str, Any]:
    """Force-reload the configuration from disk."""
    global _cache
    _cache = None
    return load_config()
