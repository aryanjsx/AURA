"""
AURA — Filesystem Sandbox.

All file operations MUST go through :func:`resolve_safe_path`.
Paths that:
- contain ``..`` traversal segments,
- are empty,
- resolve outside ``sandbox.base_dir``,
- have **any** symlink in their ancestry whose target lives outside the
  sandbox (belt-and-braces over :py:meth:`Path.resolve`),
- or land inside a configured protected system directory,

are rejected with :class:`~aura.core.errors.SandboxError`.

Symlink hardening
-----------------
``Path.resolve()`` already follows the symlink chain and the post-resolve
``relative_to(base)`` check rejects any candidate that leaves the
sandbox.  In addition, :func:`_check_symlink_chain` walks every existing
ancestor of the candidate and explicitly tests :py:meth:`Path.is_symlink`;
if any symlink resolves outside the sandbox root, the operation is
rejected **before** any filesystem write.  When the candidate itself
exists, :py:meth:`Path.resolve(strict=True)` is used so that a dangling
symlink cannot be created and silently traversed.

The sandbox base directory is read from ``sandbox.base_dir`` in
configuration and is auto-created on first use.
"""

from __future__ import annotations

import threading
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Iterable

from aura.core.config_loader import get as get_config
from aura.core.errors import SandboxError

_cached_base: Path | None = None
_base_lock = threading.Lock()

SMART_LOCATIONS: tuple[str, ...] = ("desktop", "downloads", "documents", "home")

_KEYWORD_MAP: dict[str, Path] = {
    "desktop": Path.home() / "Desktop",
    "downloads": Path.home() / "Downloads",
    "documents": Path.home() / "Documents",
    "home": Path.home(),
}


def expand_keywords(raw_path: str) -> tuple[str, bool]:
    """Expand smart keyword prefixes and tilde to real OS paths.

    Returns (expanded_path, was_expanded) where was_expanded is True if
    a keyword or tilde prefix was resolved.
    """
    stripped = raw_path.strip().strip("\"'")
    if not stripped:
        return stripped, False

    if stripped.startswith("~"):
        return str(Path(stripped).expanduser()), True

    parts = Path(stripped).parts
    if parts and parts[0].lower() in _KEYWORD_MAP:
        real_root = _KEYWORD_MAP[parts[0].lower()]
        if len(parts) > 1:
            return str(real_root / Path(*parts[1:])), True
        return str(real_root), True

    return stripped, False


def get_base_dir() -> Path:
    """Return the absolute sandbox root, creating it on first access."""
    global _cached_base
    if _cached_base is not None:
        return _cached_base
    with _base_lock:
        if _cached_base is not None:
            return _cached_base
        raw = get_config("sandbox.base_dir")
        if not raw:
            raise SandboxError("sandbox.base_dir is not configured")
        base = Path(str(raw)).expanduser().resolve()
        base.mkdir(parents=True, exist_ok=True)
        _cached_base = base
        return base


def reset_base_dir_cache() -> None:
    """Clear the cached base dir (tests only)."""
    global _cached_base
    with _base_lock:
        _cached_base = None


def _contains_traversal(raw: str) -> bool:
    # Check traversal using BOTH POSIX and Windows separator semantics so
    # a hostile caller cannot smuggle a traversal past the host by using
    # the "foreign" separator.  On Linux, ``..\\..\\etc\\passwd`` is a
    # single filename to PurePosixPath (backslash is legal in POSIX file
    # names) and would otherwise sneak through.  PureWindowsPath treats
    # both ``\`` and ``/`` as separators, so this check also catches
    # forward-slash traversal on Windows — the two views combined form a
    # superset of every viable traversal encoding.
    if ".." in PureWindowsPath(raw).parts:
        return True
    if ".." in PurePosixPath(raw).parts:
        return True
    return False


def _protected_roots() -> list[Path]:
    return [
        Path(str(p)).expanduser() for p in (get_config("paths.protected") or [])
    ]


def _is_under_protected(path: Path) -> Path | None:
    for root in _protected_roots():
        try:
            resolved_root = root.resolve()
        except OSError:
            continue
        try:
            if path == resolved_root or path.is_relative_to(resolved_root):
                return resolved_root
        except AttributeError:
            try:
                path.relative_to(resolved_root)
                return resolved_root
            except ValueError:
                continue
    return None


def _ancestor_chain(candidate: Path) -> list[Path]:
    """Return every ancestor of *candidate* from filesystem root to tip.

    Includes ``candidate`` itself (last element).  Pure lexical walk — no
    resolution — so the result is deterministic even for missing paths.
    """
    chain: list[Path] = []
    cur = candidate
    while True:
        chain.append(cur)
        parent = cur.parent
        if parent == cur:
            break
        cur = parent
    chain.reverse()
    return chain


def _check_symlink_chain(candidate: Path, base_resolved: Path) -> None:
    """Raise :class:`SandboxError` if any symlink along *candidate*'s
    ancestry resolves outside *base_resolved*.

    This is defence-in-depth on top of the standard
    ``candidate.resolve().relative_to(base)`` check: an attacker who has
    managed to plant a symlink **inside** the sandbox that points outside
    it will be rejected here before any write or read happens.
    """
    for component in _ancestor_chain(candidate):
        try:
            is_link = component.is_symlink()
        except OSError:
            # Permission errors etc. — treat as hostile and refuse.
            raise SandboxError(
                f"Cannot stat component {component}; refusing operation"
            )
        if not is_link:
            continue
        try:
            resolved = component.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            # Dangling / cyclic symlink — refuse, no write-through.
            raise SandboxError(
                f"Refusing unresolvable symlink: {component} ({exc})"
            ) from exc
        try:
            resolved.relative_to(base_resolved)
        except ValueError as exc:
            raise SandboxError(
                f"Symlink {component} escapes sandbox "
                f"(resolves to {resolved})"
            ) from exc


def resolve_safe_path(
    raw: str,
    *,
    create_parents: bool = False,
    must_exist: bool = False,
) -> Path:
    """Resolve *raw* to an absolute path guaranteed to live inside the sandbox.

    Parameters
    ----------
    raw:
        User-supplied path string.  May be relative (interpreted
        relative to the sandbox base), ``~``-prefixed, or absolute.
    create_parents:
        Create missing parent directories (inside the sandbox only).
    must_exist:
        Raise if the resolved path does not exist.

    Raises
    ------
    SandboxError
        For any traversal, escape, or protected-path violation.
    """
    if raw is None:
        raise SandboxError("Path is required")
    cleaned = str(raw).strip().strip("\"'")
    if not cleaned:
        raise SandboxError("Empty path provided")

    if _contains_traversal(cleaned):
        raise SandboxError(f"Path traversal is not allowed: {cleaned!r}")

    expanded, was_keyword = expand_keywords(cleaned)

    base = get_base_dir()
    base_resolved = base.resolve()

    path_obj = Path(expanded).expanduser()
    if path_obj.is_absolute():
        raw_candidate = path_obj
    else:
        raw_candidate = base / path_obj

    if not was_keyword:
        _check_symlink_chain(raw_candidate, base_resolved)

    # Strict resolve when the target exists (catches every remaining
    # race where a deeper component became a symlink between the
    # ancestry walk and this call).  When the target does not yet
    # exist (e.g. file.create) we resolve non-strictly.
    try:
        candidate = raw_candidate.resolve(strict=True)
    except FileNotFoundError:
        candidate = raw_candidate.resolve()
    except (OSError, RuntimeError) as exc:
        raise SandboxError(
            f"Cannot resolve path safely: {raw_candidate} ({exc})"
        ) from exc

    if not was_keyword:
        try:
            candidate.relative_to(base_resolved)
        except ValueError as exc:
            raise SandboxError(
                f"Path escapes sandbox root {base_resolved}: {candidate}"
            ) from exc

    protected = _is_under_protected(candidate)
    if protected is not None:
        raise SandboxError(
            f"Path {candidate} is inside protected directory {protected}"
        )

    if create_parents:
        # Check the parent chain for symlink escapes too before we mkdir.
        _check_symlink_chain(candidate.parent, base_resolved)
        candidate.parent.mkdir(parents=True, exist_ok=True)

    if must_exist and not candidate.exists():
        raise SandboxError(f"Path does not exist inside sandbox: {candidate}")

    return candidate


def ensure_inside_sandbox(paths: Iterable[Path]) -> None:
    """Raise :class:`SandboxError` if any path is outside the sandbox."""
    base = get_base_dir()
    for p in paths:
        resolved = Path(p).resolve()
        try:
            resolved.relative_to(base)
        except ValueError as exc:
            raise SandboxError(
                f"Path escapes sandbox root {base}: {resolved}"
            ) from exc
