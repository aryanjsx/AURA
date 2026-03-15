"""
AURA — Project Scaffolder

Generates a starter directory layout for new projects with sensible
defaults (backend/, frontend/, README, .gitignore).
"""

from __future__ import annotations

from pathlib import Path

from command_engine.logger import get_logger

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


def create_project(project_name: str, base_dir: str = ".") -> str:
    """Scaffold a new project directory.

    Creates::

        <project_name>/
        ├── backend/
        ├── frontend/
        ├── README.md
        └── .gitignore

    Parameters
    ----------
    project_name:
        Name of the project (used as directory name).
    base_dir:
        Parent directory in which the project folder is created.

    Returns
    -------
    str
        Human-readable result message.
    """
    root = Path(base_dir).resolve() / project_name

    if root.exists():
        msg = f"Directory already exists: {root}"
        logger.warning(msg)
        return msg

    try:
        (root / "backend").mkdir(parents=True, exist_ok=True)
        (root / "frontend").mkdir(parents=True, exist_ok=True)

        readme = root / "README.md"
        readme.write_text(
            f"# {project_name}\n\nProject scaffolded by AURA.\n",
            encoding="utf-8",
        )

        gitignore = root / ".gitignore"
        gitignore.write_text(_DEFAULT_GITIGNORE, encoding="utf-8")

        logger.info("Project scaffolded: %s", root)
        return f"Project '{project_name}' created at {root}"
    except OSError as exc:
        logger.error("Failed to scaffold project '%s': %s", project_name, exc)
        return f"Error creating project: {exc}"
