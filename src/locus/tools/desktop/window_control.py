"""List, focus, minimize, maximize, restore, move, resize and snap windows.

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

ACTIONS = (
    "list",
    "focus",
    "minimize",
    "maximize",
    "restore",
    "move",
    "resize",
    "snap",
)
PLACE_ACTIONS = ("move", "resize", "snap")
SNAP_POSITIONS = (
    "left",
    "right",
    "top",
    "bottom",
    "top_left",
    "top_right",
    "bottom_left",
    "bottom_right",
    "center",
)
#: Smallest window placement Locus will make, so a window can't vanish.
MIN_SIZE = 200

_PAST = {
    "focus": "Focused",
    "minimize": "Minimized",
    "maximize": "Maximized",
    "restore": "Restored",
    "move": "Moved",
    "resize": "Resized",
    "snap": "Snapped",
}

#: (left, top, width, height) in screen pixels.
Rect = Tuple[int, int, int, int]


def placement_rect(action: str, placement: dict, current: Rect, work: Rect) -> Rect:
    """Where a move, resize or snap puts a window.

    ``work`` is the usable area of the window's screen (without the taskbar
    or menu bar). Move coordinates are relative to it, and the result always
    stays inside it.
    """
    wl, wt, ww, wh = work
    cx, cy, cw, ch = current
    if action == "snap":
        position = placement["position"]
        half_w, half_h = ww // 2, wh // 2
        if position == "center":
            w, h = ww * 2 // 3, wh * 2 // 3
            return wl + (ww - w) // 2, wt + (wh - h) // 2, w, h
        x = wl + (half_w if "right" in position else 0)
        y = wt + (half_h if "bottom" in position else 0)
        w = ww if position in ("top", "bottom") else half_w
        h = wh if position in ("left", "right") else half_h
        if "right" in position:
            w = ww - half_w
        if "bottom" in position:
            h = wh - half_h
        return x, y, w, h
    if action == "resize":
        w = max(MIN_SIZE, min(int(placement["width"]), ww))
        h = max(MIN_SIZE, min(int(placement["height"]), wh))
        x, y = cx, cy
    else:  # move
        w, h = min(cw, ww), min(ch, wh)
        x, y = wl + int(placement["x"]), wt + int(placement["y"])
    x = max(wl, min(x, wl + ww - w))
    y = max(wt, min(y, wt + wh - h))
    return x, y, w, h


def _number(raw: Any) -> Union[int, None]:
    try:
        return int(round(float(raw)))
    except (TypeError, ValueError):
        return None


def _placement(action: str, params: dict) -> Union[dict, str]:
    """The move, resize or snap arguments, or a message saying what's wrong."""
    if action == "snap":
        position = params.get("position")
        if position not in SNAP_POSITIONS:
            return f"Give a position: {', '.join(SNAP_POSITIONS)}."
        return {"position": position}
    keys = ("x", "y") if action == "move" else ("width", "height")
    values = {key: _number(params.get(key)) for key in keys}
    if any(v is None for v in values.values()):
        return f"Give {' and '.join(keys)} in pixels."
    if action == "move" and any(v < 0 for v in values.values()):
        return "x and y start at the screen's top-left corner; they can't be negative."
    return values


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


def _windows_place(hwnd: int, action: str, placement: dict) -> bool:
    import ctypes
    from ctypes import wintypes

    class MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    if user32.IsIconic(hwnd) or user32.IsZoomed(hwnd):
        user32.ShowWindow(hwnd, _SW["restore"])
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    monitor = user32.MonitorFromWindow(hwnd, 2)  # MONITOR_DEFAULTTONEAREST
    user32.GetMonitorInfoW(monitor, ctypes.byref(info))
    work = info.rcWork
    x, y, w, h = placement_rect(
        action,
        placement,
        (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top),
        (work.left, work.top, work.right - work.left, work.bottom - work.top),
    )
    # SWP_NOZORDER | SWP_NOACTIVATE: change only position and size.
    return bool(user32.SetWindowPos(hwnd, 0, x, y, w, h, 0x0014))


def _windows_act(
    hwnd: int, title: str, action: str, placement: Union[dict, None] = None
) -> Union[None, str]:
    if action in PLACE_ACTIONS:
        if not _windows_place(hwnd, action, placement or {}):
            return f"Windows didn't let Locus move {title}."
        return None
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


_MAC_PLACE = """on run argv
  set appName to item 1 of argv
  set winName to item 2 of argv
  set x to (item 3 of argv) as integer
  set y to (item 4 of argv) as integer
  set w to (item 5 of argv) as integer
  set h to (item 6 of argv) as integer
  tell application "System Events"
    tell process appName
      set win to (first window whose name is winName)
      set value of attribute "AXMinimized" of win to false
      if x >= 0 and y >= 0 then set position of win to {x, y}
      if w > 0 and h > 0 then set size of win to {w, h}
    end tell
  end tell
end run"""
_MAC_SCREEN = 'tell application "Finder" to get bounds of window of desktop'
_MAC_MENU_BAR = 25


def _mac_work_area() -> Union[Rect, None]:
    done = _os.run(["osascript", "-e", _MAC_SCREEN])
    try:
        left, top, right, bottom = (int(v) for v in done.stdout.split(","))
    except ValueError:
        return None
    top = max(top, _MAC_MENU_BAR)
    return left, top, right - left, bottom - top


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


def _mac_act(
    handle: Tuple[str, str],
    title: str,
    action: str,
    placement: Union[dict, None] = None,
) -> Union[None, str]:
    app, name = handle
    if action in PLACE_ACTIONS:
        placement = placement or {}
        if action == "resize":
            x, y = -1, -1
            w, h = (max(MIN_SIZE, placement[k]) for k in ("width", "height"))
        else:
            work = _mac_work_area()
            if work is None:
                return "Couldn't read the screen size."
            if action == "move":
                x, y = work[0] + placement["x"], work[1] + placement["y"]
                w = h = -1
            else:
                x, y, w, h = placement_rect("snap", placement, work, work)
        args = [str(v) for v in (x, y, w, h)]
        done = _os.run(["osascript", "-e", _MAC_PLACE, app, name, *args])
        return None if done.ok else f"Couldn't move {title}: {done.error()}"
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


def _linux_work_area() -> Union[Rect, None]:
    done = _os.run(["wmctrl", "-d"])
    for line in done.stdout.splitlines():
        parts = line.split()
        if len(parts) > 1 and parts[1] == "*" and "WA:" in parts:
            i = parts.index("WA:")
            try:
                x, y = (int(v) for v in parts[i + 1].split(","))
                w, h = (int(v) for v in parts[i + 2].split("x"))
            except (IndexError, ValueError):
                return None
            return x, y, w, h
    return None


def _linux_act(
    window_id: str, title: str, action: str, placement: Union[dict, None] = None
) -> Union[None, str]:
    if action in PLACE_ACTIONS:
        placement = placement or {}
        if action == "resize":
            geometry = (
                -1,
                -1,
                *(max(MIN_SIZE, placement[k]) for k in ("width", "height")),
            )
        else:
            work = _linux_work_area()
            if work is None:
                return "Couldn't read the screen's work area from wmctrl."
            if action == "move":
                geometry = (work[0] + placement["x"], work[1] + placement["y"], -1, -1)
            else:
                geometry = placement_rect("snap", placement, work, work)
        _os.run(["wmctrl", "-i", "-r", window_id, "-b", _WMCTRL_STATES["restore"]])
        done = _os.run(
            ["wmctrl", "-i", "-r", window_id, "-e", "0," + ",".join(map(str, geometry))]
        )
        return None if done.ok else f"Couldn't move {title}: {done.error()}"
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
                " 'minimize', 'maximize', 'restore', 'move', 'resize' and 'snap'"
                " act on the first window whose title contains 'title' (not"
                " case-sensitive). 'move' takes x and y and 'resize' takes width"
                " and height, in pixels from the top-left of the screen's usable"
                " area. 'snap' puts the window in a 'position' (left, right, top,"
                " bottom, top_left, top_right, bottom_left, bottom_right or"
                " center). To close an app, use app_control instead."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": list(ACTIONS)},
                    "title": {
                        "type": "string",
                        "description": "Part of the window's title, like 'Notepad'.",
                    },
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                    "width": {"type": "number"},
                    "height": {"type": "number"},
                    "position": {"type": "string", "enum": list(SNAP_POSITIONS)},
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
        placement = None
        if action in PLACE_ACTIONS:
            placement = _placement(action, params)
            if isinstance(placement, str):
                return _os.fail("window_control", placement)

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
        error = (
            act_fn(handle, title, action, placement)
            if placement is not None
            else act_fn(handle, title, action)
        )
        if error:
            return _os.fail("window_control", error)
        where = (
            f" to the {placement['position'].replace('_', ' ')}"
            if action == "snap"
            else ""
        )
        return _os.ok("window_control", f"{_PAST[action]} {title}{where}.")


__all__ = ["WindowControlTool", "list_windows"]
