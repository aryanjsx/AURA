"""Tests for :mod:`aura.core.param_schema`."""
from __future__ import annotations

import pytest

from aura.core.errors import SchemaError
from aura.core.param_schema import PARAM_SCHEMAS, validate_params


def test_known_action_accepts_correct_types():
    validate_params("file.create", {"path": "hello.txt"})
    validate_params("system.cpu", {})
    validate_params("process.list", {"limit": 5})
    validate_params("process.list", {})  # optional param omitted


def test_missing_required_parameter_rejected():
    with pytest.raises(SchemaError) as e:
        validate_params("file.create", {})
    assert "Missing required parameter" in str(e.value)
    assert "'path'" in str(e.value)


def test_unknown_parameter_rejected():
    with pytest.raises(SchemaError) as e:
        validate_params("file.create", {"path": "x", "extra": "y"})
    assert "Unknown parameter" in str(e.value)
    assert "extra" in str(e.value)


@pytest.mark.parametrize(
    "bad_value",
    [123, 1.5, True, False, None, [], {}, set(), ("a",), b"bytes"],
)
def test_wrong_type_for_string_parameter_rejected(bad_value):
    with pytest.raises(SchemaError):
        validate_params("file.create", {"path": bad_value})


def test_bool_is_rejected_for_int_parameter():
    # bool is an int subclass in Python — we must still refuse it.
    with pytest.raises(SchemaError) as e:
        validate_params("process.list", {"limit": True})
    assert "bool" in str(e.value)


def test_nested_dict_rejected():
    with pytest.raises(SchemaError):
        validate_params("file.create", {"path": {"nested": "hack"}})


def test_nested_list_rejected():
    with pytest.raises(SchemaError):
        validate_params("process.shell", {"command": ["ls", "-la"]})


def test_system_cpu_accepts_empty_params_only():
    validate_params("system.cpu", {})
    with pytest.raises(SchemaError):
        validate_params("system.cpu", {"anything": "x"})


def test_non_dict_params_rejected():
    with pytest.raises(SchemaError):
        validate_params("file.create", "path=evil.txt")  # type: ignore[arg-type]


def test_non_string_parameter_key_rejected():
    with pytest.raises(SchemaError):
        validate_params("file.create", {7: "x"})  # type: ignore[dict-item]


def test_unknown_action_is_noop():
    # Opt-in model: unknown actions skip validation (registry handles
    # them).  The guarantee is for *declared* actions only.
    validate_params("definitely.not.registered", {"anything": "at all"})


def test_every_declared_schema_is_well_formed():
    """Meta-test: schemas in PARAM_SCHEMAS must themselves be sane."""
    for action, specs in PARAM_SCHEMAS.items():
        names = [s.name for s in specs]
        assert len(names) == len(set(names)), f"duplicate names in {action}"
        for s in specs:
            assert s.types, f"{action}.{s.name} has no declared types"
            for t in s.types:
                assert isinstance(t, type), f"{action}.{s.name} lists non-type {t!r}"
