"""Desktop control tools: apps, windows, settings, clipboard, notifications.

Windows is supported fully; macOS and Linux support what their standard
command-line tools allow, and say so when an action isn't available.
"""

from __future__ import annotations

from locus.tools.desktop.app_control import AppControlTool
from locus.tools.desktop.clipboard import ClipboardTool
from locus.tools.desktop.notify import NotifyTool
from locus.tools.desktop.open_path import OpenPathTool
from locus.tools.desktop.screenshot import ScreenshotTool
from locus.tools.desktop.system_control import SystemControlTool
from locus.tools.desktop.window_control import WindowControlTool

#: Registry names of every desktop tool.
DESKTOP_TOOLS = (
    "open_path",
    "app_control",
    "window_control",
    "system_control",
    "clipboard",
    "notify",
    "screenshot",
)

__all__ = [
    "DESKTOP_TOOLS",
    "AppControlTool",
    "ClipboardTool",
    "NotifyTool",
    "OpenPathTool",
    "ScreenshotTool",
    "SystemControlTool",
    "WindowControlTool",
]
