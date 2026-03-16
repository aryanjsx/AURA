"""
AURA — Centralized Path Resolution

Single source of truth for converting user-supplied path strings into
safe, absolute ``pathlib.Path`` objects.  Every module that touches the
file system must funnel paths through :func:`resolve_path` so that
``~``, smart-location keywords, and relative segments are handled
uniformly across platforms.

Smart location keywords
-----------------------
========== ====================
Keyword    Resolves to
========== ====================
desktop    ~/Desktop
downloads  ~/Downloads
documents  ~/Documents
home       ~
========== ====================
"""

from __future__ import annotations

import sys
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import FrozenSet, Optional

from command_engine.logger import get_logger

logger = get_logger("aura.path_utils")

_HOME = Path.home()

SMART_LOCATIONS: dict[str, Path] = {
    "desktop": _HOME / "Desktop",
    "downloads": _HOME / "Downloads",
    "documents": _HOME / "Documents",
    "home": _HOME,
}

_PROTECTED_ROOTS: FrozenSet[Path] = frozenset({
    Path("C:/") if sys.platform == "win32" else Path("/"),
    Path("C:/Windows") if sys.platform == "win32" else Path("/bin"),
    Path("C:/Windows/System32") if sys.platform == "win32" else Path("/usr"),
    Path("C:/Program Files") if sys.platform == "win32" else Path("/etc"),
    Path("C:/Program Files (x86)") if sys.platform == "win32" else Path("/sbin"),
})


def resolve_path(raw: str, create_parents: bool = False) -> Path:
    """Convert a user-supplied path string into a safe absolute path.

    Processing order:

    1. Strip whitespace and surrounding quotes.
    2. Expand smart-location keywords (``desktop/file.txt`` →
       ``~/Desktop/file.txt``).
    3. Expand ``~`` to the user's home directory.
    4. Resolve to an absolute path.
    5. Optionally create parent directories.

    Parameters
    ----------
    raw:
        The path string exactly as the user typed it.
    create_parents:
        If ``True``, create all parent directories that don't exist.

    Returns
    -------
    pathlib.Path
        Fully-resolved absolute path.

    Raises
    ------
    ValueError
        If the resulting path is empty or invalid.
    """
    cleaned = raw.strip().strip("\"'")
    if not cleaned:
        raise ValueError("Empty path provided.")

    cleaned = _apply_smart_locations(cleaned)

    path = Path(cleaned).expanduser().resolve()

    if create_parents:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.error("Cannot create parent dirs for %s: %s", path, exc)
            raise

    logger.debug("Resolved '%s' -> %s", raw, path)
    return path


def validate_not_protected(path: Path) -> Optional[str]:
    """Return an error message if *path* is a protected system location.

    Returns ``None`` when the path is safe to operate on.
    """
    resolved = path.resolve()

    for root in _PROTECTED_ROOTS:
        try:
            if resolved == root.resolve() or resolved.parent == root.resolve():
                msg = (
                    f"Blocked: '{resolved}' is inside a protected system "
                    f"directory ({root}). Operation aborted for safety."
                )
                logger.warning(msg)
                return msg
        except OSError:
            continue

    return None


def _apply_smart_locations(raw: str) -> str:
    """Replace a leading smart-location keyword with its real path.

    Only the **first** segment is tested (case-insensitive).
    ``desktop/file.txt`` becomes ``~/Desktop/file.txt``;
    ``my-desktop/file.txt`` is left untouched.
    """
    if sys.platform == "win32":
        parts = PureWindowsPath(raw).parts
    else:
        parts = PurePosixPath(raw).parts

    if not parts:
        return raw

    first = parts[0].lower()

    if first in SMART_LOCATIONS:
        base = SMART_LOCATIONS[first]
        remainder = Path(*parts[1:]) if len(parts) > 1 else Path()
        return str(base / remainder)

    return raw
