"""Desktop notifications, now or after a delay (timers and reminders)."""

from __future__ import annotations

import threading
from typing import Any

from locus.core.registry import ToolRegistry
from locus.core.types import ToolResult
from locus.tools._stubs import BaseTool, ToolSpec
from locus.tools.desktop import _os

#: Longest delay for a reminder: they live in the running app, not a scheduler.
MAX_DELAY_MINUTES = 24 * 60

# Toasts need an app id Windows knows; PowerShell's is always registered.
_WIN_TOAST = (
    "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications,"
    " ContentType = WindowsRuntime] | Out-Null; "
    "$xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
    "[Windows.UI.Notifications.ToastTemplateType]::ToastText02); "
    "$text = $xml.GetElementsByTagName('text'); "
    "[void]$text.Item(0).AppendChild($xml.CreateTextNode($env:LOCUS_ARG_TITLE)); "
    "[void]$text.Item(1).AppendChild($xml.CreateTextNode($env:LOCUS_ARG_MESSAGE)); "
    "$toast = [Windows.UI.Notifications.ToastNotification]::new($xml); "
    "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("
    "'{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe'"
    ").Show($toast)"
)
_MAC_NOTIFY = [
    "-e",
    "on run argv",
    "-e",
    "display notification (item 2 of argv) with title (item 1 of argv)",
    "-e",
    "end run",
]

_timers: list[threading.Timer] = []
_timers_lock = threading.Lock()


def show_notification(title: str, message: str) -> _os.Completed:
    os_name = _os.system()
    if os_name == "windows":
        return _os.powershell(_WIN_TOAST, args={"title": title, "message": message})
    if os_name == "macos":
        return _os.run(["osascript", *_MAC_NOTIFY, title, message])
    if os_name == "linux":
        return _os.run(["notify-send", title, message])
    return _os.Completed(1, "", f"Notifications aren't supported on {os_name} yet.")


def _fire(timer_ref: list, title: str, message: str) -> None:
    show_notification(title, message)
    with _timers_lock:
        if timer_ref and timer_ref[0] in _timers:
            _timers.remove(timer_ref[0])


@ToolRegistry.register("notify")
class NotifyTool(BaseTool):
    """Show a desktop notification now, or set a timer or reminder."""

    tool_id = "notify"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="notify",
            description=(
                "Show a desktop notification. With 'delay_minutes', it's a"
                " timer or reminder that appears later (up to 24 hours, while"
                " Locus stays open)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Short heading."},
                    "message": {
                        "type": "string",
                        "description": "The notification text.",
                    },
                    "delay_minutes": {
                        "type": "number",
                        "description": "Minutes to wait; 0 or empty shows it now.",
                    },
                },
                "required": ["message"],
            },
            category="desktop",
        )

    def risk_for(self, arguments: dict) -> str:
        return "read"

    def execute(self, **params: Any) -> ToolResult:
        message = str(params.get("message") or "").strip()
        if not message:
            return _os.fail("notify", "Give the notification text.")
        title = str(params.get("title") or "Locus").strip() or "Locus"
        try:
            delay = float(params.get("delay_minutes") or 0)
        except (TypeError, ValueError):
            return _os.fail("notify", "delay_minutes must be a number.")
        if not 0 <= delay <= MAX_DELAY_MINUTES:
            return _os.fail(
                "notify", "delay_minutes must be from 0 to 1440 (24 hours)."
            )

        if delay == 0:
            done = show_notification(title, message)
            if not done.ok:
                return _os.fail(
                    "notify", f"Couldn't show the notification: {done.error()}"
                )
            return _os.ok("notify", f"Showed the notification {title!r}.")

        timer_ref: list = []
        timer = threading.Timer(delay * 60, _fire, args=(timer_ref, title, message))
        timer.daemon = True
        timer_ref.append(timer)
        with _timers_lock:
            _timers.append(timer)
        timer.start()
        when = f"{delay:g} minute" + ("" if delay == 1 else "s")
        return _os.ok(
            "notify",
            f"Set a reminder {title!r} for {when} from now. It shows only if"
            " Locus is still running then.",
        )


__all__ = ["NotifyTool", "show_notification"]
