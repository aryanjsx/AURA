"""PermissionValidator tests."""
from __future__ import annotations

import pytest

from aura.core.errors import PermissionDenied
from aura.security.permissions import PermissionLevel, PermissionValidator


def test_cli_can_run_critical():
    v = PermissionValidator()
    v.validate(action="shell.run", level=PermissionLevel.CRITICAL, source="cli")


def test_llm_blocked_from_high_and_critical():
    v = PermissionValidator()
    with pytest.raises(PermissionDenied):
        v.validate(action="file.delete", level=PermissionLevel.HIGH, source="llm")
    with pytest.raises(PermissionDenied):
        v.validate(action="shell.run", level=PermissionLevel.CRITICAL, source="llm")


def test_llm_allowed_for_low_and_medium():
    v = PermissionValidator()
    v.validate(action="cpu", level=PermissionLevel.LOW, source="llm")
    v.validate(action="file.create", level=PermissionLevel.MEDIUM, source="llm")


def test_planner_capped_at_high():
    v = PermissionValidator()
    v.validate(action="file.delete", level=PermissionLevel.HIGH, source="planner")
    with pytest.raises(PermissionDenied):
        v.validate(action="shell.run", level=PermissionLevel.CRITICAL, source="planner")


def test_unknown_source_defaults_to_low():
    v = PermissionValidator()
    v.validate(action="cpu", level=PermissionLevel.LOW, source="mystery")
    with pytest.raises(PermissionDenied):
        v.validate(action="cpu", level=PermissionLevel.MEDIUM, source="mystery")


def test_permission_level_parsing():
    assert PermissionLevel.parse("low") is PermissionLevel.LOW
    assert PermissionLevel.parse("CRITICAL") is PermissionLevel.CRITICAL
    with pytest.raises(ValueError):
        PermissionLevel.parse("extreme")


# ---------------------------------------------------------------------------
# Source canonicalisation — regression guards for the whitespace /
# case-normalisation privilege-escalation bug found in the Phase-1
# destruction audit.  ``cap_for`` must do EXACT matching so that a
# caller passing ``"CLI "`` or ``"Cli"`` cannot silently inherit the
# ``cli`` cap.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("spoofed", ["CLI", "CLI ", " cli", "CLI\n", "Cli", "CLI\t"])
def test_cap_for_does_not_normalise_case_or_whitespace(spoofed: str) -> None:
    v = PermissionValidator()
    # Exact-match only: any variant of "cli" that isn't literally "cli"
    # must NOT inherit the CRITICAL cap — it must fall to the LOW
    # default for unknown sources.
    assert v.cap_for(spoofed) is PermissionLevel.LOW


def test_cap_for_canonical_sources_still_work():
    v = PermissionValidator()
    assert v.cap_for("cli") is PermissionLevel.CRITICAL
    assert v.cap_for("llm") is PermissionLevel.MEDIUM
    assert v.cap_for("planner") is PermissionLevel.HIGH
    assert v.cap_for("auto") is PermissionLevel.LOW


def test_known_sources_exposes_canonical_set():
    v = PermissionValidator()
    assert {"cli", "llm", "planner", "auto"}.issubset(v.known_sources)


@pytest.mark.parametrize("spoofed", ["CLI ", " cli", "CLI\n", "Cli"])
def test_validate_with_spoofed_cli_source_denies_critical(spoofed: str) -> None:
    v = PermissionValidator()
    with pytest.raises(PermissionDenied):
        v.validate(
            action="process.shell", level=PermissionLevel.CRITICAL, source=spoofed,
        )
