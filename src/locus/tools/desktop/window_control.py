"""List, focus, minimize, maximize and restore windows (Windows only for now)."""

from __future__ import annotations

import json
from typing import Any, List, Tuple

from locus.core.registry import ToolRegistry
from locus.core.types import ToolResult
from locus.tools._stubs import BaseTool, ToolSpec
from locus.tools.desktop import _os

ACTIONS = ("list", "focus", "minimize", "maximize", "restore")

_SW = {"minimize": 6, "maximize": 3, "restore": 9}
_GW_OWNER = 4
_GWL_EXSTYLE = -20
_WS_EX_TOOLWINDOW = 0x80
_DWMWA_CLOAKED = 14
_VK_MENU = 0x12
_KEYEVENTF_KEYUP = 0x2


def list_windows() -> List[Tuple[int, str]]:
    """``(handle, title)`` for each window a user would see in the taskbar."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    dwmapi = ctypes.windll.dwmapi  # type: ignore[attr-defined]
    found: List[Tuple[int, str]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, _GW_OWNER):
            return True
        if user32.GetWindowLongW(hwnd, _GWL_EXSTYLE) & _WS_EX_TOOLWINDOW:
            return True
        cloaked = wintypes.DWORD()
        dwmapi.DwmGetWindowAttribute(
            hwnd, _DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked)
        )
        if cloaked.value:
            return True  # suspended Store apps and other hidden windows
        length = user32.GetWindowTextLengthW(hwnd)
        if length:
            title = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, title, length + 1)
            if title.value and title.value != "Program Manager":
                found.append((int(hwnd), title.value))
        return True

    user32.EnumWindows(visit, 0)
    return found


def _apply(hwnd: int, action: str) -> bool:
    import ctypes

    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    if action == "focus":
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, _SW["restore"])
        # Windows only lets the app that last had input change the foreground
        # window; a released Alt key press counts as input.
        user32.keybd_event(_VK_MENU, 0, 0, 0)
        user32.keybd_event(_VK_MENU, 0, _KEYEVENTF_KEYUP, 0)
        return bool(user32.SetForegroundWindow(hwnd))
    user32.ShowWindow(hwnd, _SW[action])
    return True


@ToolRegistry.register("window_control")
class WindowControlTool(BaseTool):
    """Arrange open windows. Nothing here closes a window or loses work."""

    tool_id = "window_control"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="window_control",
            description=(
                "Work with open windows. 'list' shows window titles. 'focus',"
                " 'minimize', 'maximize' and 'restore' act on the first window"
                " whose title contains 'title' (not case-sensitive). To close"
                " an app, use app_control instead."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": list(ACTIONS)},
                    "title": {
                        "type": "string",
                        "description": "Part of the window's title, like 'Notepad'.",
                    },
                },
                "required": ["action"],
            },
            category="desktop",
        )

    def risk_for(self, arguments: dict) -> str:
        return "read"

    def execute(self, **params: Any) -> ToolResult:
        action = params.get("action")
        if action not in ACTIONS:
            return _os.bad_action("window_control", action, ACTIONS)
        if _os.system() != "windows":
            return _os.unsupported("window_control", "Controlling windows")
        windows = list_windows()
        if action == "list":
            titles = [title for _, title in windows]
            return _os.ok(
                "window_control", json.dumps(titles, ensure_ascii=False), titles=titles
            )
        wanted = str(params.get("title") or "").strip().lower()
        if not wanted:
            return _os.fail("window_control", "Give part of the window's title.")
        match = next(((h, t) for h, t in windows if wanted in t.lower()), None)
        if match is None:
            return _os.fail(
                "window_control", f"No open window has {wanted!r} in its title."
            )
        hwnd, title = match
        if not _apply(hwnd, action):
            return _os.fail(
                "window_control", f"Windows didn't let Locus focus {title}."
            )
        past = {
            "focus": "Focused",
            "minimize": "Minimized",
            "maximize": "Maximized",
            "restore": "Restored",
        }[action]
        return _os.ok("window_control", f"{past} {title}.")


__all__ = ["WindowControlTool", "list_windows"]
