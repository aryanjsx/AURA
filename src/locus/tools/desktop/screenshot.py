"""Save a screenshot of the whole screen."""

from __future__ import annotations

import base64
import io
import time
from pathlib import Path
from typing import Any, Optional

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


#: Screenshots sent to a model are scaled down to fit this many pixels a side.
LOOK_MAX_PIXELS = 1280


def image_for_model(path: Path) -> Optional[str]:
    """The screenshot as a base64 JPEG small enough to send to a model."""
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(path) as image:
            image = image.convert("RGB")
            image.thumbnail((LOOK_MAX_PIXELS, LOOK_MAX_PIXELS))
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=70)
    except OSError:
        return None
    return base64.b64encode(buffer.getvalue()).decode("ascii")


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
                " Returns the file's path. With look=true you also see the"
                " screenshot, to read what's on screen (needs a model that can"
                " see images)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "look": {
                        "type": "boolean",
                        "description": "Also show you the screenshot.",
                    },
                },
            },
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
        if not params.get("look"):
            return _os.ok(
                "screenshot", f"Saved a screenshot to {path}.", path=str(path)
            )
        image = image_for_model(path)
        if image is None:
            return _os.ok(
                "screenshot",
                f"Saved a screenshot to {path}, but couldn't prepare it for you"
                " to see (Pillow is needed).",
                path=str(path),
            )
        return _os.ok(
            "screenshot",
            f"Saved a screenshot to {path}. It's attached so you can see it.",
            path=str(path),
            images=[image],
        )


__all__ = ["ScreenshotTool", "screenshots_dir"]
