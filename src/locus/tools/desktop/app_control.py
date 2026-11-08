"""List, open and close desktop apps."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from typing import Any

from locus.core.registry import ToolRegistry
from locus.core.types import ToolResult
from locus.tools._stubs import BaseTool, ToolSpec
from locus.tools.desktop import _os

ACTIONS = ("list", "open", "close")

# App names only: no paths, switches or URL schemes.
_APP_NAME = re.compile(r"^[\w][\w .+\-]{0,63}$")

_WIN_LIST = (
    "Get-Process | Where-Object { $_.MainWindowTitle } | "
    "Select-Object ProcessName, Id, MainWindowTitle | ConvertTo-Json -Compress"
)
# CloseMainWindow asks the app to close, like clicking X: unsaved work prompts.
_WIN_CLOSE = (
    "$p = Get-Process -Name $env:LOCUS_ARG_NAME -ErrorAction Stop | "
    "Where-Object { $_.MainWindowHandle -ne 0 }; "
    "if (-not $p) { throw 'It has no open window.' }; "
    "$p | ForEach-Object { [void]$_.CloseMainWindow() }; @($p).Count"
)
_MAC_QUIT = [
    "-e",
    "on run argv",
    "-e",
    "tell application (item 1 of argv) to quit",
    "-e",
    "end run",
]


def _app_name(raw: object) -> str:
    name = str(raw or "").strip()
    if name.lower().endswith(".exe"):
        name = name[:-4]
    return name


@ToolRegistry.register("app_control")
class AppControlTool(BaseTool):
    """See which apps are open, open an app, or ask an app to close."""

    tool_id = "app_control"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="app_control",
            description=(
                "Work with desktop apps. 'list' shows apps that have a window"
                " open. 'open' starts an app by name (for example notepad,"
                " calc, chrome, spotify). 'close' asks an app to close, like"
                " clicking its X, so unsaved work isn't lost."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": list(ACTIONS)},
                    "name": {
                        "type": "string",
                        "description": "App name for open and close, without .exe.",
                    },
                },
                "required": ["action"],
            },
            category="desktop",
        )

    def risk_for(self, arguments: dict) -> str:
        return "read" if arguments.get("action") == "list" else "change"

    def execute(self, **params: Any) -> ToolResult:
        action = params.get("action")
        if action == "list":
            return self._list()
        if action not in ACTIONS:
            return _os.bad_action("app_control", action, ACTIONS)
        name = _app_name(params.get("name"))
        if not _APP_NAME.match(name):
            return _os.fail(
                "app_control", "Give the app's name, like notepad or chrome."
            )
        return self._open(name) if action == "open" else self._close(name)

    def _list(self) -> ToolResult:
        os_name = _os.system()
        if os_name == "windows":
            done = _os.powershell(_WIN_LIST)
            if not done.ok:
                return _os.fail("app_control", f"Couldn't list apps: {done.error()}")
            rows = json.loads(done.stdout or "[]")
            rows = [rows] if isinstance(rows, dict) else rows
            apps = [
                {"name": r["ProcessName"], "window": r["MainWindowTitle"]} for r in rows
            ]
        elif os_name == "macos":
            done = _os.run(
                [
                    "osascript",
                    "-e",
                    'tell application "System Events" to get name of '
                    "(processes where background only is false)",
                ]
            )
            if not done.ok:
                return _os.fail("app_control", f"Couldn't list apps: {done.error()}")
            apps = [{"name": n.strip()} for n in done.stdout.split(",") if n.strip()]
        else:
            return _os.unsupported("app_control", "Listing apps")
        return _os.ok("app_control", json.dumps(apps, ensure_ascii=False), apps=apps)

    def _open(self, name: str) -> ToolResult:
        os_name = _os.system()
        if os_name == "windows":
            try:
                os.startfile(name)  # type: ignore[attr-defined]
            except OSError:
                return _os.fail(
                    "app_control",
                    f"Couldn't find an app called {name}. Try its program name,"
                    " like msedge for Edge or winword for Word.",
                )
            return _os.ok("app_control", f"Opened {name}.")
        if os_name == "macos":
            done = _os.run(["open", "-a", name])
            if not done.ok:
                return _os.fail("app_control", f"Couldn't open {name}: {done.error()}")
            return _os.ok("app_control", f"Opened {name}.")
        if os_name == "linux":
            program = shutil.which(name)
            if program is None:
                return _os.fail("app_control", f"Couldn't find an app called {name}.")
            subprocess.Popen(
                [program],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return _os.ok("app_control", f"Opened {name}.")
        return _os.unsupported("app_control", "Opening apps")

    def _close(self, name: str) -> ToolResult:
        os_name = _os.system()
        if os_name == "windows":
            done = _os.powershell(_WIN_CLOSE, args={"name": name})
        elif os_name == "macos":
            done = _os.run(["osascript", *_MAC_QUIT, name])
        else:
            return _os.unsupported("app_control", "Closing apps")
        if not done.ok:
            return _os.fail("app_control", f"Couldn't close {name}: {done.error()}")
        return _os.ok("app_control", f"Asked {name} to close.")


__all__ = ["AppControlTool"]
