"""
AURA — Project Scaffolder

Generates a starter directory layout for new projects with sensible
defaults.  Folder names and generated files are loaded from config.
The target location is resolved through
:func:`~command_engine.path_utils.resolve_path` so paths like
``~/Desktop/my_project`` work as expected.
"""

from __future__ import annotations

from pathlib import Path

from command_engine.logger import get_logger
from command_engine.path_utils import resolve_path
from core.config_loader import get as get_config
from core.result import CommandResult

logger = get_logger("aura.project_scaffolder")

_DEFAULT_GITIGNORE = """\
# Python
__pycache__/
*.pyc
.env
venv/

# Node
node_modules/
dist/

# IDE
.vscode/
.idea/
"""


def _write_scaffold_file(root_name: str, filename: str, root: Path) -> None:
    """Create *filename* under *root* using templates where applicable."""
    path = root / filename
    if filename.lower() == "readme.md":
        path.write_text(
            f"# {root_name}\n\nProject scaffolded by AURA.\n",
            encoding="utf-8",
        )
    elif filename == ".gitignore":
        path.write_text(_DEFAULT_GITIGNORE, encoding="utf-8")
    else:
        path.write_text("", encoding="utf-8")


def create_project(project_name: str) -> CommandResult:
    """Scaffold a new project directory.

    *project_name* can be a bare name (``my_app``), a path with ``~``
    (``~/Desktop/my_app``), or a smart-location keyword
    (``desktop/my_app``).

    Parameters
    ----------
    project_name:
        Name or path of the project.

    Returns
    -------
    CommandResult
    """
    try:
        root = resolve_path(project_name)
    except (ValueError, OSError) as exc:
        return CommandResult(
            success=False,
            message=f"Invalid project path: {exc}",
            command_type="project.create",
        )

    if root.exists():
        msg = f"Directory already exists: {root}"
        logger.warning(msg)
        return CommandResult(success=False, message=msg, command_type="project.create")

    folders: list[str] = get_config(
        "project_scaffold.folders", ["src", "tests", "docs", "logs"]
    )
    files: list[str] = get_config(
        "project_scaffold.files", ["README.md", ".gitignore"]
    )

    try:
        for folder in folders:
            (root / folder).mkdir(parents=True, exist_ok=True)

        for filename in files:
            _write_scaffold_file(root.name, filename, root)

        logger.info("Project scaffolded: %s", root)
        return CommandResult(
            success=True,
            message=f"Project '{root.name}' created at {root}",
            data={"path": str(root), "folders": folders, "files": files},
            command_type="project.create",
        )
    except OSError as exc:
        logger.error("Failed to scaffold project '%s': %s", project_name, exc)
        return CommandResult(
            success=False,
            message=f"Error creating project: {exc}",
            command_type="project.create",
        )
