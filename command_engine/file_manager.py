"""
AURA — File Manager

Provides safe file-system operations: create, delete, rename, move,
and search.  All paths are validated before use and every action is
logged through the centralized logger.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import List

from command_engine.logger import get_logger

logger = get_logger("aura.file_manager")


def create_file(path: str) -> str:
    """Create an empty file (and parent directories if needed).

    Parameters
    ----------
    path:
        Relative or absolute file path.

    Returns
    -------
    str
        Human-readable result message.
    """
    target = Path(path).resolve()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch(exist_ok=True)
        logger.info("File created: %s", target)
        return f"File created: {target}"
    except OSError as exc:
        logger.error("Failed to create file %s: %s", target, exc)
        return f"Error creating file: {exc}"


def delete_file(path: str) -> str:
    """Delete a file if it exists.

    Returns
    -------
    str
        Human-readable result message.
    """
    target = Path(path).resolve()
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
    """Rename (or move within the same directory) a file.

    Returns
    -------
    str
        Human-readable result message.
    """
    source = Path(old_name).resolve()
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

    Returns
    -------
    str
        Human-readable result message.
    """
    src = Path(source).resolve()
    dst = Path(destination).resolve()
    if not src.exists():
        msg = f"Source file not found: {src}"
        logger.warning(msg)
        return msg
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
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
    root = Path(directory).resolve()
    if not root.is_dir():
        logger.warning("Directory not found: %s", root)
        return []
    matches = [str(p) for p in root.rglob(pattern)]
    logger.info(
        "Search in %s for '%s': %d result(s)", root, pattern, len(matches)
    )
    return matches
