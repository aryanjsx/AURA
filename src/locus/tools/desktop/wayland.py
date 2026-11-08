"""Window control on Wayland, one backend per compositor.

Wayland has no shared window API, so Locus talks to the compositor itself:
``swaymsg`` on Sway, ``hyprctl`` on Hyprland and ``kdotool`` on KDE Plasma.
GNOME doesn't let other apps control windows, so it isn't supported.
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from locus.core.types import ToolResult
from locus.tools.desktop import _os

Window = Tuple[Any, str]
Rect = Tuple[int, int, int, int]
Backend = Tuple[Callable[[], Any], Callable[..., Optional[str]]]


def is_wayland() -> bool:
    return os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland" or bool(
        os.environ.get("WAYLAND_DISPLAY")
    )


def _placement_rect(action: str, placement: dict, current: Rect, work: Rect) -> Rect:
    from locus.tools.desktop.window_control import placement_rect

    return placement_rect(action, placement, current, work)


def _json(args: List[str]) -> Union[Any, ToolResult]:
    done = _os.run(args)
    if not done.ok:
        return _os.fail("window_control", f"Couldn't list windows: {done.error()}")
    try:
        return json.loads(done.stdout or "null")
    except ValueError:
        return _os.fail("window_control", f"{args[0]} gave output Locus can't read.")


# ── Sway ─────────────────────────────────────────────────────────


def _sway_nodes(tree: Any) -> List[dict]:
    """Every window in a sway tree, including floating and scratchpad ones."""
    found: List[dict] = []
    stack = [tree] if isinstance(tree, dict) else []
    while stack:
        node = stack.pop()
        children = node.get("nodes", []) + node.get("floating_nodes", [])
        if (
            not children
            and node.get("type") in ("con", "floating_con")
            and node.get("name")
        ):
            found.append(node)
        stack.extend(children)
    return found


def _sway_windows() -> Union[List[Window], ToolResult]:
    tree = _json(["swaymsg", "-t", "get_tree", "-r"])
    if isinstance(tree, ToolResult):
        return tree
    return [(node, node["name"]) for node in _sway_nodes(tree)]


def _sway_output_rect() -> Optional[Rect]:
    outputs = _json(["swaymsg", "-t", "get_outputs", "-r"])
    if isinstance(outputs, ToolResult) or not isinstance(outputs, list):
        return None
    for output in outputs:
        if output.get("focused") and output.get("rect"):
            r = output["rect"]
            return r["x"], r["y"], r["width"], r["height"]
    return None


def _sway_act(node: dict, title: str, action: str, placement: Optional[dict] = None):
    target = f"[con_id={node['id']}]"
    commands = {
        "focus": f"{target} focus",
        "minimize": f"{target} move scratchpad",
        "maximize": f"{target} fullscreen enable",
        "restore": f"{target} scratchpad show, {target} floating disable, "
        f"{target} fullscreen disable, {target} focus",
    }
    if action in commands:
        command = commands[action]
    else:
        rect = node.get("rect", {})
        current = (
            rect.get("x", 0),
            rect.get("y", 0),
            rect.get("width", 800),
            rect.get("height", 600),
        )
        work = _sway_output_rect() or current
        x, y, w, h = _placement_rect(action, placement or {}, current, work)
        command = (
            f"{target} floating enable, {target} resize set {w} px {h} px, "
            f"{target} move absolute position {x} px {y} px"
        )
    done = _os.run(["swaymsg", command])
    return None if done.ok else f"Couldn't change {title}: {done.error()}"


# ── Hyprland ─────────────────────────────────────────────────────


def _hypr_windows() -> Union[List[Window], ToolResult]:
    clients = _json(["hyprctl", "clients", "-j"])
    if isinstance(clients, ToolResult):
        return clients
    return [(c, c["title"]) for c in clients or [] if c.get("title")]


def _hypr_monitor_rect() -> Optional[Rect]:
    monitors = _json(["hyprctl", "monitors", "-j"])
    if isinstance(monitors, ToolResult) or not isinstance(monitors, list):
        return None
    for m in monitors:
        if m.get("focused"):
            scale = float(m.get("scale") or 1) or 1
            reserved = m.get("reserved") or [0, 0, 0, 0]  # left, top, right, bottom
            width = int(m["width"] / scale) - reserved[0] - reserved[2]
            height = int(m["height"] / scale) - reserved[1] - reserved[3]
            return m["x"] + reserved[0], m["y"] + reserved[1], width, height
    return None


def _hypr_act(client: dict, title: str, action: str, placement: Optional[dict] = None):
    window = f"address:{client['address']}"
    if action == "focus":
        batches = [f"dispatch focuswindow {window}"]
    elif action == "minimize":
        # Hyprland has no minimize; a special workspace hides the window.
        batches = [f"dispatch movetoworkspacesilent special:minimized,{window}"]
    elif action == "maximize":
        batches = [f"dispatch focuswindow {window}", "dispatch fullscreen 1"]
    elif action == "restore":
        batches = [
            f"dispatch movetoworkspace e+0,{window}",
            f"dispatch focuswindow {window}",
        ]
    else:
        at, size = client.get("at", [0, 0]), client.get("size", [800, 600])
        current = (at[0], at[1], size[0], size[1])
        work = _hypr_monitor_rect() or current
        x, y, w, h = _placement_rect(action, placement or {}, current, work)
        batches = []
        if not client.get("floating"):
            batches.append(f"dispatch setfloating {window}")
        batches += [
            f"dispatch resizewindowpixel exact {w} {h},{window}",
            f"dispatch movewindowpixel exact {x} {y},{window}",
        ]
    done = _os.run(["hyprctl", "--batch", " ; ".join(batches)])
    return None if done.ok else f"Couldn't change {title}: {done.error()}"


# ── KDE Plasma (kdotool) ─────────────────────────────────────────


def _kde_windows() -> Union[List[Window], ToolResult]:
    done = _os.run(["kdotool", "search", "--name", "."])
    if not done.ok:
        return _os.fail("window_control", f"Couldn't list windows: {done.error()}")
    windows: List[Window] = []
    for window_id in done.stdout.split():
        name = _os.run(["kdotool", "getwindowname", window_id])
        if name.ok and name.stdout.strip():
            windows.append((window_id, name.stdout.strip()))
    return windows


def _kde_act(window_id: str, title: str, action: str, placement: Optional[dict] = None):
    if action in ("focus", "restore"):
        steps = [["kdotool", "windowactivate", window_id]]
    elif action == "minimize":
        steps = [["kdotool", "windowminimize", window_id]]
    elif action == "maximize":
        steps = [["kdotool", "windowstate", "--add", "MAXIMIZED", window_id]]
    else:
        placement = placement or {}
        if action == "move":
            steps = [
                [
                    "kdotool",
                    "windowmove",
                    window_id,
                    str(placement["x"]),
                    str(placement["y"]),
                ]
            ]
        elif action == "resize":
            steps = [
                [
                    "kdotool",
                    "windowsize",
                    window_id,
                    str(placement["width"]),
                    str(placement["height"]),
                ]
            ]
        else:
            return "Snapping isn't available through kdotool; use KDE's own shortcuts."
    for step in steps:
        done = _os.run(step)
        if not done.ok:
            return f"Couldn't change {title}: {done.error()}"
    return None


# ── Choosing one ─────────────────────────────────────────────────

_BACKENDS: Dict[str, Tuple[str, Backend]] = {
    "sway": ("swaymsg", (lambda: _sway_windows(), lambda *a: _sway_act(*a))),
    "hyprland": ("hyprctl", (lambda: _hypr_windows(), lambda *a: _hypr_act(*a))),
    "kde": ("kdotool", (lambda: _kde_windows(), lambda *a: _kde_act(*a))),
}


def backend() -> Union[Backend, ToolResult]:
    """The running compositor's backend, or a result explaining what's missing."""
    if os.environ.get("SWAYSOCK"):
        name = "sway"
    elif os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        name = "hyprland"
    elif "kde" in os.environ.get("XDG_CURRENT_DESKTOP", "").lower():
        name = "kde"
    else:
        desktop = os.environ.get("XDG_CURRENT_DESKTOP") or "this desktop"
        return _os.fail(
            "window_control",
            f"Window control on Wayland works on Sway, Hyprland and KDE Plasma,"
            f" not {desktop}. GNOME doesn't let apps control other windows.",
        )
    command, functions = _BACKENDS[name]
    if not _os.has_command(command):
        hint = " (install kdotool)" if name == "kde" else ""
        return _os.fail("window_control", f"{command} isn't available{hint}.")
    return functions


__all__ = ["backend", "is_wayland"]
