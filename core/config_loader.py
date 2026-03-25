"""
AURA — Configuration Loader

Loads settings from ``config.yaml`` (user-local, gitignored) with
fallback to ``config.example.yaml`` (tracked template).  If neither
file exists or PyYAML is not installed, built-in defaults are used so
that every module has a guaranteed baseline.

Usage::

    from core.config_loader import get as get_config

    level = get_config("logging.level")            # -> "INFO"
    tools = get_config("system_check.tools")        # -> ["python", ...]
    missing = get_config("no.such.key", "fallback") # -> "fallback"
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

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
            print("[WARNING] PyYAML not installed — using built-in defaults.")
        except Exception as exc:
            print(f"[WARNING] Failed to parse {path.name}: {exc}")

    _cache = _deep_merge(_DEFAULTS, raw)
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
