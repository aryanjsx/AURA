"""List, focus, minimize, maximize and restore windows.

Windows uses the window API through ctypes, macOS uses System Events (Locus
needs Accessibility permission), and Linux uses wmctrl, which works on X11
but not Wayland.
"""

from __future__ import annotations

import json
from typing import Any, Callable, List, Tuple, Union

from locus.core.registry import ToolRegistry
from locus.core.types import ToolResult
from locus.tools._stubs import BaseTool, ToolSpec
from locus.tools.desktop import _os

ACTIONS = ("list", "focus", "minimize", "maximize", "restore")

_PAST = {
    "focus": "Focused",
    "minimize": "Minimized",
    "maximize": "Maximized",
    "restore": "Restored",
}

#: (handle, title): the handle is whatever the OS needs to act on the window.
Window = Tuple[Any, str]

# ── Windows ──────────────────────────────────────────────────────

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


def _windows_act(hwnd: int, title: str, action: str) -> Union[None, str]:
    if not _apply(hwnd, action):
        return f"Windows didn't let Locus focus {title}."
    return None


# ── macOS ────────────────────────────────────────────────────────

_MAC_LIST = """set out to ""
tell application "System Events"
  repeat with p in (processes whose visible is true)
    try
      repeat with w in windows of p
        set out to out & (name of p) & tab & (name of w) & linefeed
      end repeat
    end try
  end repeat
end tell
return out"""

_MAC_ACT = """on run argv
  set appName to item 1 of argv
  set winName to item 2 of argv
  set act to item 3 of argv
  tell application "System Events"
    tell process appName
      set w to (first window whose name is winName)
      if act is "minimize" then
        set value of attribute "AXMinimized" of w to true
      else if act is "maximize" then
        set value of attribute "AXFullScreen" of w to true
      else
        set value of attribute "AXMinimized" of w to false
        set frontmost to true
        perform action "AXRaise" of w
      end if
    end tell
  end tell
end run"""


def _mac_windows() -> Union[List[Window], ToolResult]:
    done = _os.run(["osascript", "-e", _MAC_LIST])
    if not done.ok:
        return _os.fail(
            "window_control",
            "Couldn't list windows. Allow Locus under System Settings > Privacy"
            f" & Security > Accessibility. ({done.error()})",
        )
    windows: List[Window] = []
    for line in done.stdout.splitlines():
        app, _, title = line.partition("\t")
        if title.strip():
            windows.append(((app, title), title))
    return windows


def _mac_act(handle: Tuple[str, str], title: str, action: str) -> Union[None, str]:
    app, name = handle
    done = _os.run(["osascript", "-e", _MAC_ACT, app, name, action])
    return None if done.ok else f"Couldn't change {title}: {done.error()}"


# ── Linux (X11) ──────────────────────────────────────────────────

_WMCTRL_STATES = {
    "minimize": "add,hidden",
    "maximize": "add,maximized_vert,maximized_horz",
    "restore": "remove,hidden,maximized_vert,maximized_horz",
}


def _linux_windows() -> Union[List[Window], ToolResult]:
    if not _os.has_command("wmctrl"):
        return _os.fail(
            "window_control", "Install wmctrl to control windows (X11 only)."
        )
    done = _os.run(["wmctrl", "-l"])
    if not done.ok:
        return _os.fail("window_control", f"Couldn't list windows: {done.error()}")
    windows: List[Window] = []
    for line in done.stdout.splitlines():
        parts = line.split(None, 3)  # id, desktop, host, title
        if len(parts) == 4 and parts[3].strip():
            windows.append((parts[0], parts[3]))
    return windows


def _linux_act(window_id: str, title: str, action: str) -> Union[None, str]:
    if action in _WMCTRL_STATES:
        done = _os.run(["wmctrl", "-i", "-r", window_id, "-b", _WMCTRL_STATES[action]])
        if not done.ok:
            return f"Couldn't change {title}: {done.error()}"
    if action in ("focus", "restore"):
        done = _os.run(["wmctrl", "-i", "-a", window_id])
        if not done.ok:
            return f"Couldn't focus {title}: {done.error()}"
    return None


# ── Tool ─────────────────────────────────────────────────────────

# Looked up when called, so each OS's functions can be swapped out in tests.
_PLATFORMS: dict[str, Tuple[Callable[[], Any], Callable[[Any, str, str], Any]]] = {
    "windows": (lambda: list_windows(), lambda *a: _windows_act(*a)),
    "macos": (lambda: _mac_windows(), lambda *a: _mac_act(*a)),
    "linux": (lambda: _linux_windows(), lambda *a: _linux_act(*a)),
}


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
        platform = _PLATFORMS.get(_os.system())
        if platform is None:
            return _os.unsupported("window_control", "Controlling windows")
        list_fn, act_fn = platform

        windows = list_fn()
        if isinstance(windows, ToolResult):
            return windows
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
        handle, title = match
        error = act_fn(handle, title, action)
        if error:
            return _os.fail("window_control", error)
        return _os.ok("window_control", f"{_PAST[action]} {title}.")


__all__ = ["WindowControlTool", "list_windows"]
