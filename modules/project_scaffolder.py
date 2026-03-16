"""
AURA — Project Scaffolder

Generates a starter directory layout for new projects with sensible
defaults (backend/, frontend/, README, .gitignore).  The target
location is resolved through :func:`~command_engine.path_utils.resolve_path`
so paths like ``~/Desktop/my_project`` work as expected.
"""

from __future__ import annotations

from command_engine.logger import get_logger
from command_engine.path_utils import resolve_path

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


def create_project(project_name: str) -> str:
    """Scaffold a new project directory.

    *project_name* can be a bare name (``my_app``), a path with ``~``
    (``~/Desktop/my_app``), or a smart-location keyword
    (``desktop/my_app``).

    Creates::

        <project_name>/
        ├── backend/
        ├── frontend/
        ├── README.md
        └── .gitignore

    Parameters
    ----------
    project_name:
        Name or path of the project.

    Returns
    -------
    str
        Human-readable result message.
    """
    try:
        root = resolve_path(project_name)
    except (ValueError, OSError) as exc:
        return f"Invalid project path: {exc}"

    if root.exists():
        msg = f"Directory already exists: {root}"
        logger.warning(msg)
        return msg

    try:
        (root / "backend").mkdir(parents=True, exist_ok=True)
        (root / "frontend").mkdir(parents=True, exist_ok=True)

        readme = root / "README.md"
        readme.write_text(
            f"# {root.name}\n\nProject scaffolded by AURA.\n",
            encoding="utf-8",
        )

        gitignore = root / ".gitignore"
        gitignore.write_text(_DEFAULT_GITIGNORE, encoding="utf-8")

        logger.info("Project scaffolded: %s", root)
        return f"Project '{root.name}' created at {root}"
    except OSError as exc:
        logger.error("Failed to scaffold project '%s': %s", project_name, exc)
        return f"Error creating project: {exc}"
