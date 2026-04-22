"""Tests for :mod:`aura.core.config_loader`."""
from __future__ import annotations

import copy
import os

import pytest

from aura.core import config_loader
from aura.core.errors import ConfigError


@pytest.fixture(autouse=True)
def _restore_cache():
    """Snapshot + restore the module-level cache and env around each test."""
    saved_cache = config_loader._cache
    saved_env = {
        k: os.environ.get(k)
        for k in (
            "AURA_SHELL_TIMEOUT",
            "AURA_SANDBOX_DIR",
            "AURA_PROTECTED_PATHS",
            "AURA_LOG_PATH",
        )
    }
    try:
        yield
    finally:
        config_loader._cache = saved_cache
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        config_loader.reload()


def test_load_config_produces_all_required_keys() -> None:
    cfg = config_loader.reload()
    for key in config_loader.REQUIRED_KEYS:
        assert config_loader._dig(cfg, key) not in (None, "", [], {}), key


def test_missing_required_key_raises() -> None:
    # Deep-merge defaults but blank a required key, then validate manually.
    merged = copy.deepcopy(config_loader._DEFAULTS)
    merged["sandbox"]["base_dir"] = ""
    with pytest.raises(ConfigError) as excinfo:
        config_loader._validate_required(merged)
    assert "sandbox.base_dir" in str(excinfo.value)


def test_empty_required_list_raises() -> None:
    merged = copy.deepcopy(config_loader._DEFAULTS)
    merged["paths"]["protected"] = []
    with pytest.raises(ConfigError) as excinfo:
        config_loader._validate_required(merged)
    assert "paths.protected" in str(excinfo.value)


def test_missing_required_dict_raises() -> None:
    merged = copy.deepcopy(config_loader._DEFAULTS)
    merged["permissions"]["source_limits"] = {}
    with pytest.raises(ConfigError) as excinfo:
        config_loader._validate_required(merged)
    assert "permissions.source_limits" in str(excinfo.value)


def test_env_override_numeric_applies() -> None:
    os.environ["AURA_SHELL_TIMEOUT"] = "7"
    cfg = config_loader.reload()
    assert int(cfg["shell"]["timeout"]) == 7


def test_env_override_wrong_type_raises() -> None:
    os.environ["AURA_SHELL_TIMEOUT"] = "not-an-int"
    with pytest.raises(ConfigError):
        config_loader.reload()


def test_env_override_protected_paths_splits_on_comma() -> None:
    os.environ["AURA_PROTECTED_PATHS"] = "/foo, /bar ,/baz"
    cfg = config_loader.reload()
    assert cfg["paths"]["protected"] == ["/foo", "/bar", "/baz"]


def test_get_returns_default_for_missing_key() -> None:
    config_loader.reload()
    assert config_loader.get("does.not.exist", "sentinel") == "sentinel"


def test_reload_rebuilds_cache() -> None:
    cfg1 = config_loader.reload()
    cfg2 = config_loader.load_config()
    assert cfg2 is config_loader._cache
    # Same content after reload.
    assert cfg1["aura"]["name"] == cfg2["aura"]["name"]


def test_defaults_do_not_mask_missing_required_keys() -> None:
    """A *new* required key with no default must surface as missing."""
    original_required = config_loader.REQUIRED_KEYS
    try:
        config_loader.REQUIRED_KEYS = (*original_required, "not.in.defaults")
        merged = copy.deepcopy(config_loader._DEFAULTS)
        with pytest.raises(ConfigError) as excinfo:
            config_loader._validate_required(merged)
        assert "not.in.defaults" in str(excinfo.value)
    finally:
        config_loader.REQUIRED_KEYS = original_required
