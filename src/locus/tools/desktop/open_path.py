"""Open a file, folder or web page in its default app."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from locus.core.registry import ToolRegistry
from locus.core.types import ToolResult
from locus.tools._stubs import BaseTool, ToolSpec
from locus.tools.desktop import _os

#: Opening these runs a program, so the user is always asked.
EXECUTABLE_SUFFIXES = frozenset(
    {
        ".exe",
        ".msi",
        ".bat",
        ".cmd",
        ".com",
        ".ps1",
        ".vbs",
        ".vbe",
        ".js",
        ".jse",
        ".wsf",
        ".wsh",
        ".scr",
        ".lnk",
        ".url",
        ".hta",
        ".cpl",
        ".msc",
        ".jar",
        ".app",
        ".command",
        ".sh",
        ".appimage",
        ".run",
    }
)


def _is_url(target: str) -> bool:
    return urlparse(target).scheme in ("http", "https")


@ToolRegistry.register("open_path")
class OpenPathTool(BaseTool):
    """Open a file, folder or http(s) link the way double-clicking would."""

    tool_id = "open_path"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="open_path",
            description=(
                "Open a file or folder in its default app (for example a PDF in"
                " the PDF reader, or a folder in File Explorer), or an http(s)"
                " link in the default browser. Use ~ for the home folder."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File or folder path, or an http(s) URL.",
                    },
                },
                "required": ["path"],
            },
            category="desktop",
        )

    def risk_for(self, arguments: dict) -> str:
        target = str(arguments.get("path", ""))
        if _is_url(target):
            return "change"
        if Path(target).suffix.lower() in EXECUTABLE_SUFFIXES:
            return "run"
        return "read"

    def execute(self, **params: Any) -> ToolResult:
        target = str(params.get("path", "")).strip()
        if not target:
            return _os.fail("open_path", "Give a file, folder or link to open.")
        if not _is_url(target):
            # A drive letter (C:\...) parses as a one-letter scheme; any longer
            # scheme (mailto:, ms-settings:, file:) isn't a plain local path.
            if len(urlparse(target).scheme) > 1:
                return _os.fail("open_path", "Only http and https links can be opened.")
            path = Path(target).expanduser()
            if not path.exists():
                return _os.fail("open_path", f"{path} doesn't exist.")
            target = str(path.resolve())

        os_name = _os.system()
        if os_name == "windows":
            try:
                os.startfile(target)  # type: ignore[attr-defined]
            except OSError as exc:
                return _os.fail("open_path", f"Couldn't open {target}: {exc}")
            return _os.ok("open_path", f"Opened {target}.")
        if os_name == "macos":
            done = _os.run(["open", target])
        elif os_name == "linux":
            done = _os.run(["xdg-open", target])
        else:
            return _os.unsupported("open_path", "Opening files")
        if not done.ok:
            return _os.fail("open_path", f"Couldn't open {target}: {done.error()}")
        return _os.ok("open_path", f"Opened {target}.")


__all__ = ["OpenPathTool", "EXECUTABLE_SUFFIXES"]
