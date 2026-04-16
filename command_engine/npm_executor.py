"""
AURA — npm Executor

Runs ``npm`` via argv lists (never ``shell=True``) inside a validated
project directory resolved through :func:`~command_engine.path_utils.resolve_path`.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from command_engine.logger import get_logger
from command_engine.path_utils import resolve_path, validate_not_protected
from command_engine.process_manager import safe_run_command
from core.config_loader import get as get_config
from core.result import CommandResult

logger = get_logger("aura.npm_executor")


def _resolve_npm_executable() -> str | None:
    """Locate npm on PATH; on Windows prefer ``npm.cmd`` when ``npm`` is absent."""
    return shutil.which("npm") or shutil.which("npm.cmd")


def _resolve_project_dir(path_str: str) -> tuple[Path | None, str | None]:
    """Resolve *path_str* to an absolute directory and enforce path policy.

    Returns ``(path, None)`` on success, or ``(None, error_message)``.
    """
    try:
        path = resolve_path(path_str)
    except (ValueError, OSError) as exc:
        return None, f"Invalid path or permission denied: {exc}"

    if not path.is_dir():
        return None, f"Not a directory or does not exist: {path}"

    blocked = validate_not_protected(path)
    if blocked:
        return None, blocked

    return path, None


def run_npm_install(cwd: str) -> CommandResult:
    """Run ``npm install`` in *cwd* (user path string).

    Parameters
    ----------
    cwd:
        Project directory; may use ``~`` or smart-location keywords.

    Returns
    -------
    CommandResult
    """
    project, err = _resolve_project_dir(cwd)
    if err is not None or project is None:
        logger.warning("npm install blocked: %s", err)
        return CommandResult(
            success=False,
            message=err or "Invalid project directory.",
            command_type="npm.install",
        )

    npm_exec = _resolve_npm_executable()
    if npm_exec is None:
        logger.warning("npm executable not found in PATH")
        return CommandResult(
            success=False,
            message="npm executable not found in PATH",
            command_type="npm.install",
        )

    timeout = int(get_config("shell.timeout", 120))
    logger.info("npm install in %s (using %s)", project, npm_exec)
    return safe_run_command(
        [npm_exec, "install"],
        cwd=project,
        timeout=timeout,
        command_type="npm.install",
    )


def run_npm_script(script: str, cwd: str) -> CommandResult:
    """Run ``npm run <script>`` in *cwd*.

    Parameters
    ----------
    script:
        Script name from ``package.json`` ``scripts`` section.
    cwd:
        Project directory; may use ``~`` or smart-location keywords.

    Returns
    -------
    CommandResult
    """
    if not script.strip():
        return CommandResult(
            success=False,
            message="Usage: npm run <script> [project_directory]",
            command_type="npm.run",
        )

    project, err = _resolve_project_dir(cwd)
    if err is not None or project is None:
        logger.warning("npm run blocked: %s", err)
        return CommandResult(
            success=False,
            message=err or "Invalid project directory.",
            command_type="npm.run",
        )

    npm_exec = _resolve_npm_executable()
    if npm_exec is None:
        logger.warning("npm executable not found in PATH")
        return CommandResult(
            success=False,
            message="npm executable not found in PATH",
            command_type="npm.run",
        )

    timeout = int(get_config("shell.timeout", 120))
    logger.info("npm run %s in %s (using %s)", script, project, npm_exec)
    return safe_run_command(
        [npm_exec, "run", script],
        cwd=project,
        timeout=timeout,
        command_type="npm.run",
    )
