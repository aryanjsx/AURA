"""
AURA — File Manager

Provides safe file-system operations: create, delete, rename, move,
and search.  All paths are resolved through the centralized
:func:`~command_engine.path_utils.resolve_path` helper and validated
against protected system directories before any destructive action.
"""

from __future__ import annotations

import shutil
from pathlib import PurePath

from command_engine.logger import get_logger
from command_engine.path_utils import resolve_path, validate_not_protected
from core.result import CommandResult

logger = get_logger("aura.file_manager")

_SEARCH_LIMIT_DEFAULT = 200


def create_file(path: str) -> CommandResult:
    """Create an empty file (and parent directories if needed).

    Parameters
    ----------
    path:
        User-supplied file path (relative, ``~``, or smart keyword).

    Returns
    -------
    CommandResult
    """
    try:
        target = resolve_path(path, create_parents=True)
    except (ValueError, OSError) as exc:
        return CommandResult(
            success=False,
            message=f"Invalid path or permission denied: {exc}",
            command_type="file.create",
        )

    blocked = validate_not_protected(target)
    if blocked:
        return CommandResult(success=False, message=blocked, command_type="file.create")

    try:
        target.touch(exist_ok=True)
        logger.info("File created: %s", target)
        return CommandResult(
            success=True,
            message=f"File created: {target}",
            data={"path": str(target)},
            command_type="file.create",
        )
    except OSError as exc:
        logger.error("Failed to create file %s: %s", target, exc)
        return CommandResult(
            success=False,
            message=f"Error creating file: {exc}",
            command_type="file.create",
        )


def delete_file(path: str) -> CommandResult:
    """Delete a file if it exists.

    Protected system paths are blocked automatically.

    Returns
    -------
    CommandResult
    """
    try:
        target = resolve_path(path)
    except (ValueError, OSError) as exc:
        return CommandResult(
            success=False,
            message=f"Invalid path or permission denied: {exc}",
            command_type="file.delete",
        )

    blocked = validate_not_protected(target)
    if blocked:
        return CommandResult(success=False, message=blocked, command_type="file.delete")

    if not target.exists():
        msg = f"File not found: {target}"
        logger.warning(msg)
        return CommandResult(success=False, message=msg, command_type="file.delete")

    try:
        target.unlink()
        logger.info("File deleted: %s", target)
        return CommandResult(
            success=True,
            message=f"File deleted: {target}",
            data={"path": str(target)},
            command_type="file.delete",
        )
    except OSError as exc:
        logger.error("Failed to delete file %s: %s", target, exc)
        return CommandResult(
            success=False,
            message=f"Error deleting file: {exc}",
            command_type="file.delete",
        )


def rename_file(old_name: str, new_name: str) -> CommandResult:
    """Rename a file.  *new_name* must be a plain filename (no directories).

    Returns
    -------
    CommandResult
    """
    if str(PurePath(new_name).parent) != ".":
        return CommandResult(
            success=False,
            message="Error: new name must be a filename, not a path.",
            command_type="file.rename",
        )

    try:
        source = resolve_path(old_name)
    except (ValueError, OSError) as exc:
        return CommandResult(
            success=False,
            message=f"Invalid source path: {exc}",
            command_type="file.rename",
        )

    if not source.exists():
        msg = f"Source file not found: {source}"
        logger.warning(msg)
        return CommandResult(success=False, message=msg, command_type="file.rename")

    destination = source.parent / new_name

    try:
        source.rename(destination)
        logger.info("Renamed %s -> %s", source, destination)
        return CommandResult(
            success=True,
            message=f"Renamed: {source.name} -> {destination.name}",
            data={"old": str(source), "new": str(destination)},
            command_type="file.rename",
        )
    except OSError as exc:
        logger.error("Failed to rename %s: %s", source, exc)
        return CommandResult(
            success=False,
            message=f"Error renaming file: {exc}",
            command_type="file.rename",
        )


def move_file(source: str, destination: str) -> CommandResult:
    """Move a file to a new location.

    If *destination* resolves to a directory, the file is moved inside it
    keeping its original name.

    Returns
    -------
    CommandResult
    """
    try:
        src = resolve_path(source)
    except (ValueError, OSError) as exc:
        return CommandResult(
            success=False,
            message=f"Invalid source path: {exc}",
            command_type="file.move",
        )

    try:
        dst = resolve_path(destination, create_parents=True)
    except (ValueError, OSError) as exc:
        return CommandResult(
            success=False,
            message=f"Invalid destination path: {exc}",
            command_type="file.move",
        )

    blocked = validate_not_protected(dst)
    if blocked:
        return CommandResult(success=False, message=blocked, command_type="file.move")

    if not src.exists():
        msg = f"Source file not found: {src}"
        logger.warning(msg)
        return CommandResult(success=False, message=msg, command_type="file.move")

    if dst.is_dir():
        dst = dst / src.name

    try:
        shutil.move(str(src), str(dst))
        logger.info("Moved %s -> %s", src, dst)
        return CommandResult(
            success=True,
            message=f"Moved: {src} -> {dst}",
            data={"source": str(src), "destination": str(dst)},
            command_type="file.move",
        )
    except OSError as exc:
        logger.error("Failed to move %s: %s", src, exc)
        return CommandResult(
            success=False,
            message=f"Error moving file: {exc}",
            command_type="file.move",
        )


def search_files(
    directory: str,
    pattern: str,
    limit: int = _SEARCH_LIMIT_DEFAULT,
) -> CommandResult:
    """Recursively search *directory* for files matching a glob *pattern*.

    Returns
    -------
    CommandResult
        ``data["matches"]`` contains the list of matching paths.
    """
    try:
        root = resolve_path(directory)
    except (ValueError, OSError) as exc:
        logger.warning("Invalid search directory: %s", exc)
        return CommandResult(
            success=False,
            message=f"Invalid search directory: {exc}",
            command_type="file.search",
        )

    if not root.is_dir():
        logger.warning("Directory not found: %s", root)
        return CommandResult(
            success=False,
            message=f"Directory not found: {root}",
            command_type="file.search",
        )

    matches: list[str] = []
    for i, p in enumerate(root.rglob(pattern)):
        if i >= limit:
            break
        matches.append(str(p))

    logger.info(
        "Search in %s for '%s': %d result(s)", root, pattern, len(matches)
    )

    if not matches:
        return CommandResult(
            success=True,
            message="No files found.",
            data={"matches": []},
            command_type="file.search",
        )

    truncated = f" (limited to {limit})" if len(matches) >= limit else ""
    message = f"Found {len(matches)} file(s){truncated}:\n" + "\n".join(matches)
    return CommandResult(
        success=True,
        message=message,
        data={"matches": matches},
        command_type="file.search",
    )
