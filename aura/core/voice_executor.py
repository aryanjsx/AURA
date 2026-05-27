"""
AURA — Voice Command Executor.

Parses natural language system commands from the voice pipeline and
executes them directly. Handles file/folder operations, app launching,
and system queries.

Security:
  - Paths are confined to the user's home directory
  - Path traversal via '..' is rejected
  - App launching uses a strict allowlist (APP_MAP)
  - No shell execution — all subprocess calls use list form
"""

from __future__ import annotations

import logging
import os
import pathlib
import platform
import re
import subprocess

import psutil

logger = logging.getLogger("aura.voice_executor")

HOME = pathlib.Path.home().resolve()

# Validated app launcher map — only these apps can be opened via voice
APP_MAP: dict[str, list[str]] = {
    "chrome":    ["cmd", "/c", "start", "chrome"],
    "firefox":   ["cmd", "/c", "start", "firefox"],
    "vscode":    ["code"],
    "vs code":   ["code"],
    "spotify":   ["cmd", "/c", "start", "spotify"],
    "notepad":   ["notepad"],
    "terminal":  ["cmd"],
    "explorer":  ["explorer"],
    "edge":      ["cmd", "/c", "start", "msedge"],
    "brave":     ["cmd", "/c", "start", "brave"],
    "calculator":["calc"],
    "paint":     ["mspaint"],
    "word":      ["cmd", "/c", "start", "winword"],
    "excel":     ["cmd", "/c", "start", "excel"],
    "powerpoint":["cmd", "/c", "start", "powerpnt"],
}

# Additional map for macOS/Linux
_MACOS_APP_MAP: dict[str, list[str]] = {
    "chrome":    ["open", "-a", "Google Chrome"],
    "firefox":   ["open", "-a", "Firefox"],
    "vscode":    ["code"],
    "vs code":   ["code"],
    "spotify":   ["open", "-a", "Spotify"],
    "terminal":  ["open", "-a", "Terminal"],
}

_LINUX_APP_MAP: dict[str, list[str]] = {
    "chrome":    ["google-chrome"],
    "firefox":   ["firefox"],
    "vscode":    ["code"],
    "vs code":   ["code"],
    "spotify":   ["spotify"],
    "terminal":  ["x-terminal-emulator"],
    "notepad":   ["gedit"],
    "explorer":  ["xdg-open", str(HOME)],
}

_PATH_ALIASES: dict[str, pathlib.Path] = {
    "desktop":   HOME / "Desktop",
    "documents": HOME / "Documents",
    "downloads": HOME / "Downloads",
    "home":      HOME,
}


def _validate_path(raw_path: str) -> pathlib.Path:
    """Validate and resolve a path, ensuring it stays within HOME.

    Raises ValueError if the resolved path escapes the user's home directory.
    Never accepts paths containing '..' or absolute paths outside HOME.
    """
    if ".." in raw_path:
        raise ValueError(f"Path traversal rejected: {raw_path!r}")
    p = (HOME / raw_path).resolve()
    if not str(p).startswith(str(HOME)):
        raise ValueError(f"Path outside home directory rejected: {p}")
    return p


def _safe_join(base: pathlib.Path, name: str) -> pathlib.Path:
    """Safely join a base path with a name component.

    Rejects names containing path separators or traversal sequences.
    """
    if ".." in name or "/" in name or "\\" in name:
        raise ValueError(f"Invalid name component: {name!r}")
    target = (base / name).resolve()
    if not str(target).startswith(str(base.resolve())):
        raise ValueError(f"Resolved path escapes base: {target}")
    return target


def execute(text: str) -> str:
    """Parse and execute a voice system command. Returns a spoken response."""
    lower = text.lower().strip()

    # File/folder creation
    m = re.search(
        r"(?:create|make)\s+(?:a\s+)?(?:new\s+)?(file|folder|directory)\s+(?:named?|called)?\s*(\S+)\s+(?:in|on|at)\s+(.+)",
        lower,
    )
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
    m = re.search(
        r"(?:delete|remove)\s+(?:the\s+)?(?:file|folder|directory)\s+(?:named?|called)?\s*(\S+)\s+(?:in|on|from)\s+(.+)",
        lower,
    )
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

    if re.search(r"\b(battery)\b", lower):
        try:
            battery = psutil.sensors_battery()
            if battery:
                return f"Battery is at {battery.percent} percent, {'charging' if battery.power_plugged else 'on battery'}."
            return "No battery information available."
        except Exception:
            return "Could not read battery status."

    if re.search(r"\b(disk|storage)\b", lower):
        disk = psutil.disk_usage("/")
        used_gb = disk.used / (1024 ** 3)
        total_gb = disk.total / (1024 ** 3)
        return f"Disk usage is {used_gb:.1f} of {total_gb:.1f} gigabytes, {disk.percent} percent."

    return ""


def _resolve_path(location: str) -> pathlib.Path | None:
    """Resolve a spoken location to a validated path within HOME."""
    loc = location.lower().strip().rstrip(".")
    for alias, path in _PATH_ALIASES.items():
        if alias in loc:
            return path

    # Try to validate as a path within HOME
    try:
        return _validate_path(location)
    except ValueError as exc:
        logger.warning("Path rejected: %s", exc)
        return None


def _create(kind: str, name: str, location: str) -> str:
    base = _resolve_path(location)
    if base is None:
        return "I can't create files in that location."

    name = name.strip("'\"")
    try:
        target = _safe_join(base, name)
    except ValueError as exc:
        logger.warning("Name rejected: %s", exc)
        return f"Invalid name: {name}."

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
        return "I can't delete files in that location."

    name = name.strip("'\"")
    try:
        target = _safe_join(base, name)
    except ValueError as exc:
        logger.warning("Name rejected: %s", exc)
        return f"Invalid name: {name}."

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
    """Open an application by name using the validated APP_MAP."""
    key = app_name.lower().strip()
    system = platform.system()

    # Select the correct app map for the platform
    if system == "Windows":
        app_map = APP_MAP
    elif system == "Darwin":
        app_map = _MACOS_APP_MAP
    else:
        app_map = _LINUX_APP_MAP

    if key not in app_map:
        return f"App '{app_name}' is not in the allowed launcher list."

    try:
        subprocess.Popen(app_map[key])  # list form, no shell execution
        return f"Opening {app_name}."
    except Exception as exc:
        logger.error("Failed to open %s: %s", app_name, exc)
        return f"Could not open {app_name}."


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
