"""Desktop notifications, now or later (timers and reminders).

Reminders are saved in ``~/.locus/reminders.json``, so they survive a
restart: :func:`restore_reminders` (called when ``locus serve`` starts)
schedules them again and shows any that came due while Locus was closed.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from locus.core.registry import ToolRegistry
from locus.core.types import ToolResult
from locus.tools._stubs import BaseTool, ToolSpec
from locus.tools.desktop import _os

ACTIONS = ("notify", "list_reminders", "cancel_reminder")

#: Longest delay for a reminder (30 days).
MAX_DELAY_MINUTES = 30 * 24 * 60

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


def show_notification(title: str, message: str) -> _os.Completed:
    os_name = _os.system()
    if os_name == "windows":
        return _os.powershell(_WIN_TOAST, args={"title": title, "message": message})
    if os_name == "macos":
        return _os.run(["osascript", *_MAC_NOTIFY, title, message])
    if os_name == "linux":
        return _os.run(["notify-send", title, message])
    return _os.Completed(1, "", f"Notifications aren't supported on {os_name} yet.")


# ── Saved reminders ──────────────────────────────────────────────


class ReminderStore:
    """Pending reminders: ``{id, title, message, due_at}`` (epoch seconds)."""

    def __init__(self, path: Optional[Path] = None) -> None:
        if path is None:
            from locus.core.paths import get_config_dir

            path = Path(get_config_dir()) / "reminders.json"
        self.path = Path(path)
        self._lock = threading.Lock()

    def _load(self) -> List[Dict[str, Any]]:
        try:
            rows = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return [r for r in rows if isinstance(r, dict) and r.get("id")]

    def _save(self, rows: List[Dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(rows, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def add(self, title: str, message: str, due_at: float) -> Dict[str, Any]:
        entry = {
            "id": uuid.uuid4().hex[:8],
            "title": title,
            "message": message,
            "due_at": due_at,
        }
        with self._lock:
            self._save(self._load() + [entry])
        return entry

    def remove(self, reminder_id: str) -> bool:
        with self._lock:
            rows = self._load()
            kept = [r for r in rows if r["id"] != reminder_id]
            if len(kept) == len(rows):
                return False
            self._save(kept)
            return True

    def all(self) -> List[Dict[str, Any]]:
        with self._lock:
            return sorted(self._load(), key=lambda r: r.get("due_at", 0))


_store: Optional[ReminderStore] = None
_timers: Dict[str, threading.Timer] = {}
_timers_lock = threading.Lock()


def get_store() -> ReminderStore:
    global _store
    with _timers_lock:
        if _store is None:
            _store = ReminderStore()
        return _store


def _fire(entry: Dict[str, Any], missed: bool = False) -> None:
    title = entry["title"] + (" (missed while Locus was closed)" if missed else "")
    show_notification(title, entry["message"])
    get_store().remove(entry["id"])
    with _timers_lock:
        _timers.pop(entry["id"], None)


def _schedule(entry: Dict[str, Any]) -> None:
    delay = max(0.0, float(entry["due_at"]) - time.time())
    timer = threading.Timer(delay, _fire, args=(entry,))
    timer.daemon = True
    with _timers_lock:
        if entry["id"] in _timers:
            return
        _timers[entry["id"]] = timer
    timer.start()


def restore_reminders() -> int:
    """Schedule saved reminders again; show any that came due while closed.

    Returns how many reminders were restored.
    """
    now = time.time()
    entries = get_store().all()
    for entry in entries:
        if float(entry.get("due_at", 0)) <= now:
            threading.Thread(target=_fire, args=(entry, True), daemon=True).start()
        else:
            _schedule(entry)
    return len(entries)


def _when(seconds: float) -> str:
    minutes = seconds / 60
    if minutes < 90:
        return f"{minutes:g} minute" + ("" if minutes == 1 else "s")
    return time.strftime("%a %d %b at %H:%M", time.localtime(time.time() + seconds))


# ── Tool ─────────────────────────────────────────────────────────


@ToolRegistry.register("notify")
class NotifyTool(BaseTool):
    """Show a desktop notification now, or set, list or cancel reminders."""

    tool_id = "notify"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="notify",
            description=(
                "Desktop notifications and reminders. 'notify' (the default)"
                " shows 'message' now, or after 'delay_minutes' as a timer or"
                " reminder (up to 30 days; saved, so it still comes after"
                " Locus restarts). 'list_reminders' shows pending reminders;"
                " 'cancel_reminder' cancels the one with 'id'."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": list(ACTIONS)},
                    "title": {"type": "string", "description": "Short heading."},
                    "message": {
                        "type": "string",
                        "description": "The notification text.",
                    },
                    "delay_minutes": {
                        "type": "number",
                        "description": "Minutes to wait; 0 or empty shows it now.",
                    },
                    "id": {
                        "type": "string",
                        "description": "Reminder id, for cancel_reminder.",
                    },
                },
            },
            category="desktop",
        )

    def risk_for(self, arguments: dict) -> str:
        return "read"

    def execute(self, **params: Any) -> ToolResult:
        action = params.get("action") or "notify"
        if action not in ACTIONS:
            return _os.bad_action("notify", action, ACTIONS)
        if action == "list_reminders":
            return self._list()
        if action == "cancel_reminder":
            return self._cancel(str(params.get("id") or ""))

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
                "notify", "delay_minutes must be from 0 to 43200 (30 days)."
            )

        if delay == 0:
            done = show_notification(title, message)
            if not done.ok:
                return _os.fail(
                    "notify", f"Couldn't show the notification: {done.error()}"
                )
            return _os.ok("notify", f"Showed the notification {title!r}.")

        entry = get_store().add(title, message, time.time() + delay * 60)
        _schedule(entry)
        return _os.ok(
            "notify",
            f"Set a reminder {title!r} for {_when(delay * 60)} from now"
            f" (id {entry['id']}). If Locus is closed then, it shows the next"
            " time Locus starts.",
            reminder=entry,
        )

    @staticmethod
    def _list() -> ToolResult:
        entries = get_store().all()
        if not entries:
            return _os.ok("notify", "No reminders are set.", reminders=[])
        lines = [
            f"{e['id']}: {e['title']} - {e['message']} (in "
            f"{_when(max(0.0, e['due_at'] - time.time()))})"
            for e in entries
        ]
        return _os.ok("notify", "\n".join(lines), reminders=entries)

    @staticmethod
    def _cancel(reminder_id: str) -> ToolResult:
        if not reminder_id:
            return _os.fail("notify", "Give the reminder's id (see list_reminders).")
        if not get_store().remove(reminder_id):
            return _os.fail("notify", f"No reminder has the id {reminder_id!r}.")
        with _timers_lock:
            timer = _timers.pop(reminder_id, None)
        if timer is not None:
            timer.cancel()
        return _os.ok("notify", f"Cancelled reminder {reminder_id}.")


__all__ = [
    "NotifyTool",
    "ReminderStore",
    "get_store",
    "restore_reminders",
    "show_notification",
]
