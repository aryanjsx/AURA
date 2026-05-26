"""
AURA — Voice Command Executor.

Parses natural language system commands from the voice pipeline and
executes them directly. Handles file/folder operations, app launching,
and system queries.

Security: paths are resolved relative to well-known user directories
(Desktop, Documents, Downloads, Home). Protected system paths are blocked.
"""

from __future__ import annotations

import logging
import os
import platform
import re
import subprocess
from pathlib import Path

import psutil

logger = logging.getLogger("aura.voice_executor")

_USER_HOME = Path.home()

_PATH_ALIASES: dict[str, Path] = {
    "desktop": _USER_HOME / "Desktop",
    "documents": _USER_HOME / "Documents",
    "downloads": _USER_HOME / "Downloads",
    "home": _USER_HOME,
}

_PROTECTED = {
    "C:\\Windows", "C:\\Program Files", "C:\\Program Files (x86)",
    "/bin", "/usr", "/etc", "/sbin", "/boot", "/System", "/Library",
}


def execute(text: str) -> str:
    """Parse and execute a voice system command. Returns a spoken response."""
    lower = text.lower().strip()

    # File/folder creation
    m = re.search(r"(?:create|make)\s+(?:a\s+)?(?:new\s+)?(file|folder|directory)\s+(?:named?|called)?\s*(\S+)\s+(?:in|on|at)\s+(.+)", lower)
    if m:
        kind, name, location = m.group(1), m.group(2), m.group(3).strip().rstrip(".")
        return _create(kind, name, location)

    m = re.search(r"(?:create|make)\s+(?:a\s+)?(?:new\s+)?(file|folder|directory)\s+(.+)", lower)
    if m:
        kind = m.group(1)
        rest = m.group(2).strip().rstrip(".")
        parts = re.split(r"\s+(?:in|on|at)\s+", rest, maxsplit=1)
        if len(parts) == 2:
            return _create(kind, parts[0], parts[1])
        return _create(kind, rest, "desktop")

    # File/folder deletion
    m = re.search(r"(?:delete|remove)\s+(?:the\s+)?(?:file|folder|directory)\s+(?:named?|called)?\s*(\S+)\s+(?:in|on|from)\s+(.+)", lower)
    if m:
        return _delete(m.group(1), m.group(2).strip().rstrip("."))

    m = re.search(r"(?:delete|remove)\s+(?:the\s+)?(?:file|folder|directory)\s+(.+)", lower)
    if m:
        name = m.group(1).strip().rstrip(".")
        return _delete(name, "desktop")

    # Open application
    m = re.search(r"(?:open|launch|start)\s+(.+)", lower)
    if m:
        return _open_app(m.group(1).strip().rstrip("."))

    # Kill process
    m = re.search(r"(?:kill|stop|close|end)\s+(?:the\s+)?(?:process\s+)?(.+)", lower)
    if m:
        return _kill_process(m.group(1).strip().rstrip("."))

    # System info
    if re.search(r"\bcpu\b", lower):
        usage = psutil.cpu_percent(interval=0.5)
        return f"CPU usage is {usage} percent."

    if re.search(r"\b(ram|memory)\b", lower):
        mem = psutil.virtual_memory()
        used_gb = mem.used / (1024 ** 3)
        total_gb = mem.total / (1024 ** 3)
        return f"Memory usage is {used_gb:.1f} of {total_gb:.1f} gigabytes, {mem.percent} percent."

    return ""


def _resolve_path(location: str) -> Path | None:
    """Resolve a spoken location to a real path."""
    loc = location.lower().strip().rstrip(".")
    for alias, path in _PATH_ALIASES.items():
        if alias in loc:
            return path

    candidate = Path(location)
    if candidate.is_absolute():
        for protected in _PROTECTED:
            if str(candidate).startswith(protected):
                return None
        return candidate

    return _PATH_ALIASES.get("desktop", _USER_HOME / "Desktop")


def _create(kind: str, name: str, location: str) -> str:
    base = _resolve_path(location)
    if base is None:
        return f"I can't create files in protected system directories."

    name = name.strip("'\"")
    target = base / name

    try:
        if kind in ("folder", "directory"):
            target.mkdir(parents=True, exist_ok=True)
            return f"Folder {name} created on {base.name}."
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.touch(exist_ok=True)
            return f"File {name} created on {base.name}."
    except Exception as exc:
        logger.error("Create failed: %s", exc)
        return f"Failed to create {name}: {exc}"


def _delete(name: str, location: str) -> str:
    base = _resolve_path(location)
    if base is None:
        return "I can't delete files in protected system directories."

    name = name.strip("'\"")
    target = base / name

    if not target.exists():
        return f"{name} not found on {base.name}."

    try:
        if target.is_dir():
            import shutil
            shutil.rmtree(target)
            return f"Folder {name} deleted from {base.name}."
        else:
            target.unlink()
            return f"File {name} deleted from {base.name}."
    except Exception as exc:
        logger.error("Delete failed: %s", exc)
        return f"Failed to delete {name}: {exc}"


def _open_app(app_name: str) -> str:
    """Open an application by name."""
    app = app_name.strip().rstrip(".")
    system = platform.system()

    try:
        if system == "Windows":
            os.startfile(app)
        elif system == "Darwin":
            subprocess.Popen(["open", "-a", app])
        else:
            subprocess.Popen([app])
        return f"Opening {app}."
    except Exception:
        try:
            if system == "Windows":
                subprocess.Popen(["start", app], shell=True)
                return f"Opening {app}."
        except Exception:
            pass
        return f"Could not open {app}."


def _kill_process(name: str) -> str:
    name = name.strip().rstrip(".")
    killed = 0
    for proc in psutil.process_iter(["name"]):
        try:
            if name.lower() in proc.info["name"].lower():
                proc.terminate()
                killed += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if killed:
        return f"Terminated {killed} {name} process{'es' if killed > 1 else ''}."
    return f"No {name} process found."
