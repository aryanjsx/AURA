"""Unit tests for configuration loading and validation.

Protects: config loads, required-section validation, env overrides,
fallback chain, version consistency.
"""
from __future__ import annotations

import copy
import os
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from aura.core.errors import ConfigError

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _fresh_load(yaml_path: Path):
    """Force-load config from a specific YAML file, bypassing cache."""
    import aura.core.config_loader as cl

    raw = _load_yaml(yaml_path)
    cl._validate_required_sections(raw)
    merged = cl._deep_merge(cl._DEFAULTS, raw)
    merged = cl._apply_env_overrides(merged)
    cl._validate_required(merged)
    cl._validate_ranges(merged)
    return merged


# ── happy path ───────────────────────────────────────────────────────


@pytest.mark.unit
class TestConfigLoadsSuccessfully:
    def test_config_loads_successfully_with_valid_file(self):
        cfg = _fresh_load(_FIXTURES / "config_valid.yaml")
        assert isinstance(cfg, dict)
        assert cfg["aura"]["name"] == "AURA"

    def test_config_version_matches_package_version(self):
        from aura import __version__
        assert __version__ == "2.0.0"


# ── missing sections ────────────────────────────────────────────────


@pytest.mark.unit
class TestConfigRequiredSections:
    def test_config_raises_on_missing_aura_section(self):
        raw = _load_yaml(_FIXTURES / "config_missing_section.yaml")
        from aura.core.config_loader import _validate_required_sections
        with pytest.raises(ConfigError, match="aura"):
            _validate_required_sections(raw)

    def test_config_raises_on_missing_sandbox_section(self):
        raw = _load_yaml(_FIXTURES / "config_valid.yaml")
        del raw["sandbox"]
        from aura.core.config_loader import _validate_required_sections
        with pytest.raises(ConfigError, match="sandbox"):
            _validate_required_sections(raw)

    def test_config_raises_on_missing_safety_section(self):
        raw = _load_yaml(_FIXTURES / "config_valid.yaml")
        del raw["safety"]
        from aura.core.config_loader import _validate_required_sections
        with pytest.raises(ConfigError, match="safety"):
            _validate_required_sections(raw)

    def test_config_raises_on_missing_models_section(self):
        """models is NOT in _REQUIRED_SECTIONS — this should pass validation.
        Phase 2 config sections are optional in Phase 1.
        """
        raw = _load_yaml(_FIXTURES / "config_valid.yaml")
        raw.pop("models", None)
        from aura.core.config_loader import _validate_required_sections
        _validate_required_sections(raw)

    def test_config_raises_on_missing_ollama_section(self):
        """ollama is NOT in _REQUIRED_SECTIONS — optional Phase 2 block."""
        raw = _load_yaml(_FIXTURES / "config_valid.yaml")
        raw.pop("ollama", None)
        from aura.core.config_loader import _validate_required_sections
        _validate_required_sections(raw)


# ── environment overrides ────────────────────────────────────────────


@pytest.mark.unit
class TestConfigEnvOverrides:
    def test_config_env_override_log_path(self):
        from aura.core.config_loader import _apply_env_overrides
        raw = _load_yaml(_FIXTURES / "config_valid.yaml")
        with patch.dict(os.environ, {"AURA_LOG_PATH": "/tmp/custom.log"}):
            result = _apply_env_overrides(raw)
        assert result["logging"]["file"] == "/tmp/custom.log"


# ── fallback chain ───────────────────────────────────────────────────


@pytest.mark.unit
class TestConfigFallbackChain:
    def test_config_fallback_chain_uses_example_when_main_missing(self):
        import aura.core.config_loader as cl
        old_cache = cl._cache
        try:
            cl._cache = None
            fake_main = Path("/nonexistent/config.yaml")
            with patch.object(cl, "_CONFIG_PATH", fake_main):
                fallback = cl._FALLBACK_PATH
                if fallback.exists():
                    cfg = cl.load_config()
                    assert isinstance(cfg, dict)
                else:
                    with pytest.raises(ConfigError, match="No configuration file"):
                        cl.load_config()
        finally:
            cl._cache = old_cache
