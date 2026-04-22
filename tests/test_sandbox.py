"""Filesystem sandbox tests."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from aura.core.errors import SandboxError
from aura.core.sandbox import get_base_dir, resolve_safe_path


def test_relative_path_resolves_inside_base():
    base = get_base_dir()
    result = resolve_safe_path("inside.txt", create_parents=True)
    assert str(result).startswith(str(base))


def test_dotdot_traversal_rejected():
    with pytest.raises(SandboxError):
        resolve_safe_path("../../etc/passwd")
    with pytest.raises(SandboxError):
        resolve_safe_path("..\\..\\etc\\passwd")


def test_absolute_path_outside_base_rejected(tmp_path: Path):
    target = tmp_path / "escape.txt"
    target.write_text("x")
    with pytest.raises(SandboxError):
        resolve_safe_path(str(target))


def test_protected_directory_rejected():
    # Pick an entry that exists in defaults.
    protected = "C:/Windows" if os.name == "nt" else "/etc"
    with pytest.raises(SandboxError):
        resolve_safe_path(protected)


def test_must_exist_flag_enforced():
    with pytest.raises(SandboxError):
        resolve_safe_path("definitely-not-there-xyz", must_exist=True)


def test_create_parents_creates_missing_directories():
    p = resolve_safe_path("nested/a/b/c.txt", create_parents=True)
    assert p.parent.is_dir()


# ---------------------------------------------------------------------------
# Symlink-escape hardening
# ---------------------------------------------------------------------------
def _supports_symlinks(tmp_path: Path) -> bool:
    """Symlinks on Windows need either admin or developer mode."""
    src = tmp_path / "_probe_src"
    src.write_text("x")
    link = tmp_path / "_probe_link"
    try:
        os.symlink(src, link)
    except (OSError, NotImplementedError):
        return False
    return link.is_symlink()


def test_symlink_inside_sandbox_pointing_outside_is_blocked(tmp_path):
    base = get_base_dir()
    if not _supports_symlinks(tmp_path):
        pytest.skip("symlinks unsupported on this host")

    outside_target = tmp_path / "outside_target"
    outside_target.write_text("secret")

    # Plant a symlink *inside* the sandbox pointing to the outside target.
    link = base / "evil_link"
    if link.exists() or link.is_symlink():
        link.unlink()
    os.symlink(outside_target, link)
    try:
        # (a) direct access to the symlinked file must fail
        with pytest.raises(SandboxError):
            resolve_safe_path("evil_link", must_exist=True)
        # (b) creation through the symlink must fail too
        with pytest.raises(SandboxError):
            resolve_safe_path("evil_link/child.txt", create_parents=True)
    finally:
        try:
            link.unlink()
        except OSError:
            pass


def test_symlink_chain_escaping_sandbox_is_blocked(tmp_path):
    base = get_base_dir()
    if not _supports_symlinks(tmp_path):
        pytest.skip("symlinks unsupported on this host")

    outside = tmp_path / "outside_dir"
    outside.mkdir()
    (outside / "victim.txt").write_text("pwned")

    hop1 = base / "hop1"
    hop2 = base / "hop2"
    for h in (hop1, hop2):
        if h.exists() or h.is_symlink():
            h.unlink()
    os.symlink(outside, hop1)     # hop1 -> outside
    os.symlink(hop1, hop2)        # hop2 -> hop1 -> outside
    try:
        with pytest.raises(SandboxError):
            resolve_safe_path("hop2/victim.txt", must_exist=True)
        with pytest.raises(SandboxError):
            resolve_safe_path("hop2", must_exist=True)
    finally:
        for h in (hop2, hop1):
            try:
                h.unlink()
            except OSError:
                pass


def test_dangling_symlink_inside_sandbox_is_refused(tmp_path):
    base = get_base_dir()
    if not _supports_symlinks(tmp_path):
        pytest.skip("symlinks unsupported on this host")

    nowhere = tmp_path / "definitely_missing_xyz"
    dangling = base / "dangling_link"
    if dangling.exists() or dangling.is_symlink():
        dangling.unlink()
    os.symlink(nowhere, dangling)
    try:
        # dangling link points outside sandbox → resolve() lands outside
        # base, or strict resolve raises — either way must SandboxError.
        with pytest.raises(SandboxError):
            resolve_safe_path("dangling_link")
    finally:
        try:
            dangling.unlink()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Pure-logic tests of the symlink guard — these run on every platform
# (including hosts where os.symlink is not permitted) because they drive
# _check_symlink_chain with monkey-patched Path objects.
# ---------------------------------------------------------------------------
def test_check_symlink_chain_rejects_external_target(tmp_path, monkeypatch):
    from aura.core import sandbox as sandbox_mod

    base = tmp_path / "sandbox"
    base.mkdir()
    base_resolved = base.resolve()
    candidate = base / "evil_link"

    # Patch Path.is_symlink so the candidate appears to be a symlink.
    original_is_symlink = Path.is_symlink

    def fake_is_symlink(self):
        if self == candidate:
            return True
        return original_is_symlink(self)

    # Patch Path.resolve so the "symlink" appears to resolve outside base.
    original_resolve = Path.resolve

    def fake_resolve(self, strict=False):
        if self == candidate:
            return tmp_path / "outside_target"
        return original_resolve(self, strict=strict)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)
    monkeypatch.setattr(Path, "resolve", fake_resolve)

    with pytest.raises(SandboxError) as excinfo:
        sandbox_mod._check_symlink_chain(candidate, base_resolved)
    assert "escapes sandbox" in str(excinfo.value)


def test_check_symlink_chain_rejects_unresolvable_link(tmp_path, monkeypatch):
    from aura.core import sandbox as sandbox_mod

    base = tmp_path / "sandbox"
    base.mkdir()
    base_resolved = base.resolve()
    candidate = base / "dangling"

    original_is_symlink = Path.is_symlink
    original_resolve = Path.resolve

    def fake_is_symlink(self):
        if self == candidate:
            return True
        return original_is_symlink(self)

    def fake_resolve(self, strict=False):
        if self == candidate and strict:
            raise FileNotFoundError(str(self))
        return original_resolve(self, strict=strict)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)
    monkeypatch.setattr(Path, "resolve", fake_resolve)

    with pytest.raises(SandboxError) as excinfo:
        sandbox_mod._check_symlink_chain(candidate, base_resolved)
    assert "unresolvable" in str(excinfo.value).lower()


def test_check_symlink_chain_accepts_internal_link(tmp_path, monkeypatch):
    """A symlink whose target stays inside the sandbox must be allowed."""
    from aura.core import sandbox as sandbox_mod

    base = tmp_path / "sandbox"
    base.mkdir()
    inside_target = base / "inside_target"
    inside_target.write_text("ok")
    base_resolved = base.resolve()
    candidate = base / "friendly_link"

    original_is_symlink = Path.is_symlink
    original_resolve = Path.resolve

    def fake_is_symlink(self):
        if self == candidate:
            return True
        return original_is_symlink(self)

    def fake_resolve(self, strict=False):
        if self == candidate:
            return inside_target
        return original_resolve(self, strict=strict)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)
    monkeypatch.setattr(Path, "resolve", fake_resolve)

    sandbox_mod._check_symlink_chain(candidate, base_resolved)  # must NOT raise


def test_check_symlink_chain_rejects_parent_escape(tmp_path, monkeypatch):
    """When a mid-chain component is a symlink escaping the sandbox,
    the deeper candidate must be refused even if the candidate itself
    is not a symlink."""
    from aura.core import sandbox as sandbox_mod

    base = tmp_path / "sandbox"
    base.mkdir()
    base_resolved = base.resolve()
    bad_parent = base / "parent_link"
    candidate = bad_parent / "child.txt"

    original_is_symlink = Path.is_symlink
    original_resolve = Path.resolve

    def fake_is_symlink(self):
        if self == bad_parent:
            return True
        return original_is_symlink(self)

    def fake_resolve(self, strict=False):
        if self == bad_parent:
            return tmp_path / "outside_parent"
        return original_resolve(self, strict=strict)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)
    monkeypatch.setattr(Path, "resolve", fake_resolve)

    with pytest.raises(SandboxError) as excinfo:
        sandbox_mod._check_symlink_chain(candidate, base_resolved)
    assert "parent_link" in str(excinfo.value) or "escapes" in str(excinfo.value)


def test_resolve_safe_path_refuses_symlink_when_os_privileged(tmp_path, monkeypatch):
    """Simulate the real resolve_safe_path by patching Path.resolve so
    the candidate *would* escape even though we never touched the
    filesystem with a real symlink."""
    from aura.core import sandbox as sandbox_mod

    # Point the sandbox at a fresh tmp dir for this single test.
    sandbox_mod.reset_base_dir_cache()
    monkeypatch.setattr(
        sandbox_mod, "get_base_dir", lambda: tmp_path / "sandbox_x"
    )
    (tmp_path / "sandbox_x").mkdir()

    target_outside = tmp_path / "external.txt"
    target_outside.write_text("secret")

    original_resolve = Path.resolve

    def fake_resolve(self, strict=False):
        # Simulate a symlink at 'bad' that resolves outside.
        if self.name == "bad":
            return target_outside
        return original_resolve(self, strict=strict)

    monkeypatch.setattr(Path, "resolve", fake_resolve)

    with pytest.raises(SandboxError):
        sandbox_mod.resolve_safe_path("bad")

    sandbox_mod.reset_base_dir_cache()


def test_symlink_entirely_inside_sandbox_is_permitted(tmp_path):
    base = get_base_dir()
    if not _supports_symlinks(tmp_path):
        pytest.skip("symlinks unsupported on this host")

    inside_target = base / "real_target"
    inside_target.write_text("ok")
    link = base / "internal_link"
    if link.exists() or link.is_symlink():
        link.unlink()
    os.symlink(inside_target, link)
    try:
        resolved = resolve_safe_path("internal_link", must_exist=True)
        assert resolved == inside_target.resolve()
    finally:
        try:
            link.unlink()
        except OSError:
            pass
        try:
            inside_target.unlink()
        except OSError:
            pass
