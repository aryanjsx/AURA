"""Save a screenshot of the whole screen."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from locus.core.registry import ToolRegistry
from locus.core.types import ToolResult
from locus.tools._stubs import BaseTool, ToolSpec
from locus.tools.desktop import _os

_WIN_SCREENSHOT = (
    "Add-Type -AssemblyName System.Windows.Forms, System.Drawing; "
    "$b = [System.Windows.Forms.SystemInformation]::VirtualScreen; "
    "$img = New-Object System.Drawing.Bitmap $b.Width, $b.Height; "
    "$g = [System.Drawing.Graphics]::FromImage($img); "
    "$g.CopyFromScreen($b.Left, $b.Top, 0, 0, $img.Size); "
    "$img.Save($env:LOCUS_ARG_PATH, [System.Drawing.Imaging.ImageFormat]::Png); "
    "$g.Dispose(); $img.Dispose()"
)


def screenshots_dir() -> Path:
    from locus.core.paths import get_config_dir

    return Path(get_config_dir()) / "screenshots"


@ToolRegistry.register("screenshot")
class ScreenshotTool(BaseTool):
    """Capture every screen into a PNG in Locus's screenshots folder."""

    tool_id = "screenshot"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="screenshot",
            description=(
                "Take a screenshot of the whole screen and save it as a PNG."
                " Returns the file's path."
            ),
            parameters={"type": "object", "properties": {}},
            category="desktop",
        )

    def risk_for(self, arguments: dict) -> str:
        # The screen can show private messages, passwords or documents.
        return "change"

    def execute(self, **params: Any) -> ToolResult:
        folder = screenshots_dir()
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / time.strftime("screenshot-%Y%m%d-%H%M%S.png")

        os_name = _os.system()
        if os_name == "windows":
            done = _os.powershell(_WIN_SCREENSHOT, args={"path": str(path)})
        elif os_name == "macos":
            done = _os.run(["screencapture", "-x", str(path)])
        elif os_name == "linux":
            if _os.has_command("gnome-screenshot"):
                done = _os.run(["gnome-screenshot", "-f", str(path)])
            elif _os.has_command("grim"):
                done = _os.run(["grim", str(path)])
            else:
                return _os.fail(
                    "screenshot",
                    "Install gnome-screenshot or grim to take screenshots.",
                )
        else:
            return _os.unsupported("screenshot", "Screenshots")
        if not done.ok or not path.exists():
            return _os.fail("screenshot", f"Couldn't take a screenshot: {done.error()}")
        return _os.ok("screenshot", f"Saved a screenshot to {path}.", path=str(path))


__all__ = ["ScreenshotTool", "screenshots_dir"]
