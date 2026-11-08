"""Read and write the clipboard's text."""

from __future__ import annotations

from typing import Any

from locus.core.registry import ToolRegistry
from locus.core.types import ToolResult
from locus.tools._stubs import BaseTool, ToolSpec
from locus.tools.desktop import _os

ACTIONS = ("read", "write")

#: Long clipboard contents are cut so they don't flood the model's context.
MAX_READ_CHARS = 10_000


def _linux_commands(action: str) -> list[list[str]]:
    if action == "read":
        return [
            ["wl-paste", "--no-newline"],
            ["xclip", "-selection", "clipboard", "-o"],
        ]
    return [["wl-copy"], ["xclip", "-selection", "clipboard"]]


@ToolRegistry.register("clipboard")
class ClipboardTool(BaseTool):
    """Copy text to, or read text from, the clipboard."""

    tool_id = "clipboard"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="clipboard",
            description=(
                "'read' returns the text on the clipboard. 'write' puts 'text'"
                " on the clipboard so the user can paste it."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": list(ACTIONS)},
                    "text": {
                        "type": "string",
                        "description": "Text to copy, for write.",
                    },
                },
                "required": ["action"],
            },
            category="desktop",
        )

    def risk_for(self, arguments: dict) -> str:
        # Reading can expose passwords or private text the user copied.
        return "change"

    def execute(self, **params: Any) -> ToolResult:
        action = params.get("action")
        if action not in ACTIONS:
            return _os.bad_action("clipboard", action, ACTIONS)
        text = str(params.get("text") or "")
        if action == "write" and not text:
            return _os.fail("clipboard", "Give the text to copy.")

        os_name = _os.system()
        if os_name == "windows":
            done = (
                _os.powershell("Get-Clipboard -Raw")
                if action == "read"
                else _os.powershell(
                    "Set-Clipboard -Value ([Console]::In.ReadToEnd())", input=text
                )
            )
        elif os_name == "macos":
            done = (
                _os.run(["pbpaste"])
                if action == "read"
                else _os.run(["pbcopy"], input=text)
            )
        elif os_name == "linux":
            commands = [c for c in _linux_commands(action) if _os.has_command(c[0])]
            if not commands:
                return _os.fail(
                    "clipboard", "Install wl-clipboard or xclip to use the clipboard."
                )
            done = _os.run(commands[0], input=None if action == "read" else text)
        else:
            return _os.unsupported("clipboard", "The clipboard")
        if not done.ok:
            return _os.fail("clipboard", f"Couldn't use the clipboard: {done.error()}")

        if action == "write":
            return _os.ok(
                "clipboard", f"Copied {len(text)} characters to the clipboard."
            )
        content = done.stdout.rstrip("\r\n") if os_name == "windows" else done.stdout
        if not content:
            return _os.ok("clipboard", "The clipboard has no text.")
        if len(content) > MAX_READ_CHARS:
            content = (
                content[:MAX_READ_CHARS] + "\n[cut off: the clipboard has more text]"
            )
        return _os.ok("clipboard", content)


__all__ = ["ClipboardTool"]
