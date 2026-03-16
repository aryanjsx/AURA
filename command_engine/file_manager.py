"""
AURA — File Manager

Provides safe file-system operations: create, delete, rename, move,
and search.  All paths are resolved through the centralized
:func:`~command_engine.path_utils.resolve_path` helper and validated
against protected system directories before any destructive action.
"""

from __future__ import annotations

import shutil
from typing import List

from command_engine.logger import get_logger
from command_engine.path_utils import resolve_path, validate_not_protected

logger = get_logger("aura.file_manager")


def create_file(path: str) -> str:
    """Create an empty file (and parent directories if needed).

    Parameters
    ----------
    path:
        User-supplied file path (relative, ``~``, or smart keyword).

    Returns
    -------
    str
        Human-readable result message.
    """
    try:
        target = resolve_path(path, create_parents=True)
    except (ValueError, OSError) as exc:
        return f"Invalid path or permission denied: {exc}"

    try:
        target.touch(exist_ok=True)
        logger.info("File created: %s", target)
        return f"File created: {target}"
    except OSError as exc:
        logger.error("Failed to create file %s: %s", target, exc)
        return f"Error creating file: {exc}"


def delete_file(path: str) -> str:
    """Delete a file if it exists.

    Protected system paths are blocked automatically.

    Returns
    -------
    str
        Human-readable result message.
    """
    try:
        target = resolve_path(path)
    except (ValueError, OSError) as exc:
        return f"Invalid path or permission denied: {exc}"

    blocked = validate_not_protected(target)
    if blocked:
        return blocked

    if not target.exists():
        msg = f"File not found: {target}"
        logger.warning(msg)
        return msg

    try:
        target.unlink()
        logger.info("File deleted: %s", target)
        return f"File deleted: {target}"
    except OSError as exc:
        logger.error("Failed to delete file %s: %s", target, exc)
        return f"Error deleting file: {exc}"


def rename_file(old_name: str, new_name: str) -> str:
    """Rename a file.  *new_name* is placed in the same directory as *old_name*.

    Returns
    -------
    str
        Human-readable result message.
    """
    try:
        source = resolve_path(old_name)
    except (ValueError, OSError) as exc:
        return f"Invalid source path: {exc}"

    if not source.exists():
        msg = f"Source file not found: {source}"
        logger.warning(msg)
        return msg

    destination = source.parent / new_name

    try:
        source.rename(destination)
        logger.info("Renamed %s -> %s", source, destination)
        return f"Renamed: {source.name} -> {destination.name}"
    except OSError as exc:
        logger.error("Failed to rename %s: %s", source, exc)
        return f"Error renaming file: {exc}"


def move_file(source: str, destination: str) -> str:
    """Move a file to a new location.

    If *destination* resolves to a directory, the file is moved inside it
    keeping its original name.

    Returns
    -------
    str
        Human-readable result message.
    """
    try:
        src = resolve_path(source)
    except (ValueError, OSError) as exc:
        return f"Invalid source path: {exc}"

    try:
        dst = resolve_path(destination, create_parents=True)
    except (ValueError, OSError) as exc:
        return f"Invalid destination path: {exc}"

    if not src.exists():
        msg = f"Source file not found: {src}"
        logger.warning(msg)
        return msg

    if dst.is_dir():
        dst = dst / src.name

    try:
        shutil.move(str(src), str(dst))
        logger.info("Moved %s -> %s", src, dst)
        return f"Moved: {src} -> {dst}"
    except OSError as exc:
        logger.error("Failed to move %s: %s", src, exc)
        return f"Error moving file: {exc}"


def search_files(directory: str, pattern: str) -> List[str]:
    """Recursively search *directory* for files matching a glob *pattern*.

    Returns
    -------
    list[str]
        List of matching file paths (as strings).
    """
    try:
        root = resolve_path(directory)
    except (ValueError, OSError) as exc:
        logger.warning("Invalid search directory: %s", exc)
        return []

    if not root.is_dir():
        logger.warning("Directory not found: %s", root)
        return []

    matches = [str(p) for p in root.rglob(pattern)]
    logger.info(
        "Search in %s for '%s': %d result(s)", root, pattern, len(matches)
    )
    return matches
