"""Desktop control tools, with the OS layer faked so nothing touches the desktop."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from locus.server.approvals import tool_risk
from locus.tools.desktop import (
    AppControlTool,
    ClipboardTool,
    NotifyTool,
    OpenPathTool,
    ScreenshotTool,
    SystemControlTool,
    WindowControlTool,
    _os,
    app_control,
    notify,
    open_path,
    window_control,
)


@pytest.fixture(autouse=True)
def _isolate_reminders(tmp_path, monkeypatch):
    """Keep reminders out of the real ``~/.locus`` and drop leftover timers."""
    monkeypatch.setattr(notify, "_store", notify.ReminderStore(tmp_path / "rem.json"))
    monkeypatch.setattr(notify, "_timers", {})


class FakeOS:
    """Records commands instead of running them."""

    def __init__(self, monkeypatch, system="windows", stdout="", returncode=0):
        self.calls: list[dict] = []
        self.stdout = stdout
        self.returncode = returncode
        self.on_call = None
        monkeypatch.setattr(_os, "system", lambda: system)
        monkeypatch.setattr(_os, "run", self._run)
        monkeypatch.setattr(_os, "powershell", self._powershell)
        monkeypatch.setattr(_os, "has_command", lambda name: True)

    def _done(self, call):
        self.calls.append(call)
        if self.on_call:
            self.on_call(call)
        return _os.Completed(
            self.returncode, self.stdout, "boom" if self.returncode else ""
        )

    def _run(self, args, *, env=None, input=None, timeout=0):
        return self._done({"args": args, "input": input})

    def _powershell(self, script, *, args=None, input=None, timeout=0):
        return self._done({"script": script, "args": args or {}, "input": input})


# ── Risk levels ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "tool, arguments, risk",
    [
        (OpenPathTool(), {"path": "C:/docs/report.pdf"}, "read"),
        (OpenPathTool(), {"path": "C:/downloads/setup.EXE"}, "run"),
        (OpenPathTool(), {"path": "C:/x/run.ps1"}, "run"),
        (OpenPathTool(), {"path": "https://example.com"}, "change"),
        (AppControlTool(), {"action": "list"}, "read"),
        (AppControlTool(), {"action": "open", "name": "notepad"}, "change"),
        (AppControlTool(), {"action": "close", "name": "notepad"}, "change"),
        (WindowControlTool(), {"action": "minimize", "title": "x"}, "read"),
        (SystemControlTool(), {"action": "get_volume"}, "read"),
        (SystemControlTool(), {"action": "set_volume", "level": 20}, "change"),
        (SystemControlTool(), {"action": "lock_screen"}, "change"),
        (ClipboardTool(), {"action": "read"}, "change"),
        (ClipboardTool(), {"action": "write", "text": "x"}, "change"),
        (NotifyTool(), {"message": "hi"}, "read"),
        (ScreenshotTool(), {}, "change"),
    ],
)
def test_risk_depends_on_the_call(tool, arguments, risk):
    assert tool_risk(tool.spec.name, tool, arguments) == risk


def test_a_broken_risk_for_asks():
    class Broken:
        def risk_for(self, arguments):
            raise RuntimeError

    class Odd:
        def risk_for(self, arguments):
            return "harmless"

    assert tool_risk("x", Broken(), {}) == "change"
    assert tool_risk("x", Odd(), {}) == "change"


# ── open_path ────────────────────────────────────────────────────


def test_open_path_opens_existing_files_on_windows(monkeypatch, tmp_path):
    FakeOS(monkeypatch, "windows")
    opened = []
    monkeypatch.setattr(open_path.os, "startfile", opened.append, raising=False)
    target = tmp_path / "notes.txt"
    target.write_text("x")

    result = OpenPathTool().execute(path=str(target))

    assert result.success
    assert opened == [str(target.resolve())]


def test_open_path_uses_xdg_open_on_linux(monkeypatch, tmp_path):
    fake = FakeOS(monkeypatch, "linux")
    assert OpenPathTool().execute(path=str(tmp_path)).success
    assert fake.calls[0]["args"] == ["xdg-open", str(tmp_path.resolve())]


@pytest.mark.parametrize(
    "path, message",
    [
        ("", "Give a file"),
        ("~/definitely-missing-locus-file.txt", "doesn't exist"),
        ("ms-settings:display", "Only http and https"),
        ("file:///C:/x.txt", "Only http and https"),
    ],
)
def test_open_path_refuses(monkeypatch, path, message):
    FakeOS(monkeypatch, "macos")
    result = OpenPathTool().execute(path=path)
    assert not result.success
    assert message in result.content


def test_open_path_opens_links_without_checking_the_disk(monkeypatch):
    fake = FakeOS(monkeypatch, "macos")
    assert OpenPathTool().execute(path="https://example.com/a").success
    assert fake.calls[0]["args"] == ["open", "https://example.com/a"]


# ── app_control ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "stdout",
    [
        json.dumps({"ProcessName": "notepad", "Id": 1, "MainWindowTitle": "a.txt"}),
        json.dumps([{"ProcessName": "notepad", "Id": 1, "MainWindowTitle": "a.txt"}]),
    ],
)
def test_app_list_on_windows(monkeypatch, stdout):
    FakeOS(monkeypatch, "windows", stdout=stdout)
    result = AppControlTool().execute(action="list")
    assert result.metadata["apps"] == [{"name": "notepad", "window": "a.txt"}]


def test_app_open_on_windows_uses_the_shell(monkeypatch):
    FakeOS(monkeypatch, "windows")
    opened = []
    monkeypatch.setattr(app_control.os, "startfile", opened.append, raising=False)
    assert AppControlTool().execute(action="open", name="notepad.exe").success
    assert opened == ["notepad"]


@pytest.mark.parametrize(
    "name", ["", "C:\\Windows\\cmd.exe", "../evil", "a;b", "ms-settings:", "x" * 80]
)
def test_app_names_must_be_plain(monkeypatch, name):
    fake = FakeOS(monkeypatch, "windows")
    result = AppControlTool().execute(action="open", name=name)
    assert not result.success
    assert fake.calls == []


def test_app_close_passes_the_name_outside_the_script(monkeypatch):
    fake = FakeOS(monkeypatch, "windows", stdout="1")
    assert AppControlTool().execute(action="close", name="notepad").success
    call = fake.calls[0]
    assert call["args"] == {"name": "notepad"}
    assert "notepad" not in call["script"]
    assert "CloseMainWindow" in call["script"]


def test_app_close_on_macos_quits_by_name(monkeypatch):
    fake = FakeOS(monkeypatch, "macos")
    assert AppControlTool().execute(action="close", name="Safari").success
    assert fake.calls[0]["args"][0] == "osascript"
    assert fake.calls[0]["args"][-1] == "Safari"


def test_app_errors_are_reported(monkeypatch):
    FakeOS(monkeypatch, "windows", returncode=1)
    result = AppControlTool().execute(action="close", name="notepad")
    assert not result.success
    assert "boom" in result.content


# ── window_control ───────────────────────────────────────────────


def test_windows_are_matched_by_part_of_the_title(monkeypatch):
    FakeOS(monkeypatch, "windows")
    applied = []
    monkeypatch.setattr(
        window_control,
        "list_windows",
        lambda: [(1, "Inbox - Outlook"), (2, "notes.txt - Notepad")],
    )
    monkeypatch.setattr(
        window_control,
        "_apply",
        lambda hwnd, action: applied.append((hwnd, action)) or True,
    )

    result = WindowControlTool().execute(action="minimize", title="notepad")

    assert result.success
    assert result.content == "Minimized notes.txt - Notepad."
    assert applied == [(2, "minimize")]
    listed = WindowControlTool().execute(action="list")
    assert listed.metadata["titles"] == ["Inbox - Outlook", "notes.txt - Notepad"]
    assert not WindowControlTool().execute(action="focus", title="excel").success


def test_window_control_on_macos_uses_system_events(monkeypatch):
    fake = FakeOS(monkeypatch, "macos", stdout="Safari\tApple\nNotes\tShopping list\n")

    listed = WindowControlTool().execute(action="list")
    result = WindowControlTool().execute(action="minimize", title="shopping")

    assert listed.metadata["titles"] == ["Apple", "Shopping list"]
    assert result.content == "Minimized Shopping list."
    args = fake.calls[-1]["args"]
    assert args[0] == "osascript"
    assert args[-3:] == ["Notes", "Shopping list", "minimize"]


def test_window_control_on_macos_explains_accessibility(monkeypatch):
    FakeOS(monkeypatch, "macos", returncode=1)
    result = WindowControlTool().execute(action="list")
    assert "Accessibility" in result.content


def test_window_control_on_linux_uses_wmctrl(monkeypatch):
    fake = FakeOS(
        monkeypatch,
        "linux",
        stdout="0x01 0 host Terminal\n0x02 0 host notes.txt - gedit\n",
    )

    result = WindowControlTool().execute(action="restore", title="GEDIT")

    assert result.content == "Restored notes.txt - gedit."
    calls = [c["args"] for c in fake.calls[1:]]
    assert calls == [
        [
            "wmctrl",
            "-i",
            "-r",
            "0x02",
            "-b",
            "remove,hidden,maximized_vert,maximized_horz",
        ],
        ["wmctrl", "-i", "-a", "0x02"],
    ]


def test_window_control_on_linux_needs_wmctrl(monkeypatch):
    FakeOS(monkeypatch, "linux")
    monkeypatch.setattr(_os, "has_command", lambda name: False)
    assert "wmctrl" in WindowControlTool().execute(action="list").content


def test_window_control_on_other_systems(monkeypatch):
    FakeOS(monkeypatch, "freebsd")
    result = WindowControlTool().execute(action="list")
    assert "isn't supported on freebsd" in result.content


# ── system_control ───────────────────────────────────────────────


def test_volume_level_goes_in_as_an_argument(monkeypatch):
    fake = FakeOS(monkeypatch, "windows")
    assert SystemControlTool().execute(action="set_volume", level=35).success
    call = fake.calls[0]
    assert call["args"] == {"level": 35}
    assert "$env:LOCUS_ARG_LEVEL" in call["script"]


def test_reading_the_volume_on_windows(monkeypatch):
    FakeOS(monkeypatch, "windows", stdout="42 True\n")
    result = SystemControlTool().execute(action="get_volume")
    assert result.content == "Volume is 42% and muted."
    assert result.metadata == {"volume": 42, "muted": True}


@pytest.mark.parametrize("level", [None, -1, 101, "loud"])
def test_levels_must_be_0_to_100(monkeypatch, level):
    fake = FakeOS(monkeypatch, "windows")
    result = SystemControlTool().execute(action="set_volume", level=level)
    assert not result.success
    assert fake.calls == []


def test_brightness_failure_explains_why(monkeypatch):
    FakeOS(monkeypatch, "windows", returncode=1)
    result = SystemControlTool().execute(action="set_brightness", level=50)
    assert "built-in laptop screens" in result.content


def test_macos_volume_and_lock(monkeypatch):
    fake = FakeOS(monkeypatch, "macos")
    assert SystemControlTool().execute(action="set_volume", level=20).success
    assert "set volume output volume 20" in fake.calls[0]["args"][-1]
    assert SystemControlTool().execute(action="lock_screen").success
    assert fake.calls[1]["args"] == ["pmset", "displaysleepnow"]
    assert not SystemControlTool().execute(action="set_brightness", level=5).success


def test_linux_volume_uses_pactl(monkeypatch):
    fake = FakeOS(monkeypatch, "linux", stdout="Volume: front-left: 1 / 55% / -15 dB")
    result = SystemControlTool().execute(action="get_volume")
    assert result.metadata["volume"] == 55
    SystemControlTool().execute(action="mute")
    assert fake.calls[-1]["args"] == ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1"]


# ── clipboard ────────────────────────────────────────────────────


def test_clipboard_text_goes_through_stdin(monkeypatch):
    fake = FakeOS(monkeypatch, "windows")
    assert ClipboardTool().execute(action="write", text="'; Remove-Item x").success
    call = fake.calls[0]
    assert call["input"] == "'; Remove-Item x"
    assert "Remove-Item" not in call["script"]


def test_long_clipboard_text_is_cut(monkeypatch):
    from locus.tools.desktop.clipboard import MAX_READ_CHARS

    FakeOS(monkeypatch, "macos", stdout="x" * (MAX_READ_CHARS + 5))
    result = ClipboardTool().execute(action="read")
    assert result.content.startswith("x" * MAX_READ_CHARS)
    assert "cut off" in result.content


def test_empty_clipboard(monkeypatch):
    FakeOS(monkeypatch, "windows", stdout="\r\n")
    assert (
        ClipboardTool().execute(action="read").content == "The clipboard has no text."
    )


def test_linux_clipboard_needs_a_helper(monkeypatch):
    FakeOS(monkeypatch, "linux")
    monkeypatch.setattr(_os, "has_command", lambda name: False)
    result = ClipboardTool().execute(action="read")
    assert "wl-clipboard or xclip" in result.content


# ── notify ───────────────────────────────────────────────────────


def test_notification_now_passes_text_as_arguments(monkeypatch):
    fake = FakeOS(monkeypatch, "windows")
    assert NotifyTool().execute(title="Tea", message="It's ready").success
    call = fake.calls[0]
    assert call["args"] == {"title": "Tea", "message": "It's ready"}
    assert "It's ready" not in call["script"]


def test_reminders_wait(monkeypatch):
    FakeOS(monkeypatch, "linux")
    started = []

    class FakeTimer:
        def __init__(self, seconds, function, args):
            self.seconds, self.function, self.args = seconds, function, args
            self.daemon = False

        def start(self):
            started.append(self)

        def cancel(self):
            started.remove(self)

    monkeypatch.setattr(notify.threading, "Timer", FakeTimer)

    result = NotifyTool().execute(message="Stand up", delay_minutes=2.5)

    assert result.success
    assert "2.5 minutes from now" in result.content
    assert started[0].seconds == pytest.approx(150, abs=2)
    assert started[0].daemon is True
    saved = notify.get_store().all()
    assert [r["message"] for r in saved] == ["Stand up"]

    listed = NotifyTool().execute(action="list_reminders")
    assert "Stand up" in listed.content
    reminder_id = saved[0]["id"]
    assert NotifyTool().execute(action="cancel_reminder", id=reminder_id).success
    assert notify.get_store().all() == []
    assert started == []
    assert not NotifyTool().execute(action="cancel_reminder", id=reminder_id).success


def test_reminders_are_restored_after_a_restart(monkeypatch):
    import time as _time

    fake = FakeOS(monkeypatch, "linux")
    store = notify.get_store()
    future = store.add("Call", "Ring the bank", _time.time() + 3600)
    store.add("Meds", "Take them", _time.time() - 60)
    scheduled = []
    monkeypatch.setattr(notify, "_schedule", scheduled.append)

    class Inline:
        def __init__(self, target, args, daemon):
            self.target, self.args = target, args

        def start(self):
            self.target(*self.args)

    monkeypatch.setattr(notify.threading, "Thread", Inline)

    assert notify.restore_reminders() == 2

    assert [e["id"] for e in scheduled] == [future["id"]]
    # The one that came due while Locus was closed shows now and is done.
    assert fake.calls[0]["args"] == [
        "notify-send",
        "Meds (missed while Locus was closed)",
        "Take them",
    ]
    assert [r["id"] for r in store.all()] == [future["id"]]


@pytest.mark.parametrize("delay", [-1, 50000, "soon"])
def test_reminder_delays_are_checked(monkeypatch, delay):
    FakeOS(monkeypatch, "linux")
    assert not NotifyTool().execute(message="x", delay_minutes=delay).success


def test_notifications_need_text(monkeypatch):
    FakeOS(monkeypatch, "linux")
    assert not NotifyTool().execute(message="  ").success


# ── screenshot ───────────────────────────────────────────────────


def test_screenshot_is_saved_in_the_locus_folder(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCUS_HOME", str(tmp_path))
    fake = FakeOS(monkeypatch, "windows")
    fake.on_call = lambda call: Path(call["args"]["path"]).write_bytes(b"png")

    result = ScreenshotTool().execute()

    assert result.success
    saved = Path(result.metadata["path"])
    assert saved.parent == tmp_path / "screenshots"
    assert saved.suffix == ".png"


def test_screenshot_reports_failure(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCUS_HOME", str(tmp_path))
    FakeOS(monkeypatch, "macos")  # no file is written
    assert not ScreenshotTool().execute().success


# ── Registration ─────────────────────────────────────────────────


def test_every_desktop_tool_has_a_spec_and_risk():
    from locus.tools.desktop import DESKTOP_TOOLS

    tools = [
        OpenPathTool(),
        AppControlTool(),
        WindowControlTool(),
        SystemControlTool(),
        ClipboardTool(),
        NotifyTool(),
        ScreenshotTool(),
    ]
    assert sorted(t.spec.name for t in tools) == sorted(DESKTOP_TOOLS)
    for tool in tools:
        assert tool.spec.category == "desktop"
        assert callable(tool.risk_for)


# ── Wi-Fi and Bluetooth ──────────────────────────────────────────


def test_radio_state_is_read_on_windows(monkeypatch):
    FakeOS(monkeypatch, "windows", stdout="WiFi On\nBluetooth Off\n")
    result = SystemControlTool().execute(action="get_radios")
    assert result.content == "Wi-Fi: on; Bluetooth: off"
    assert result.metadata["radios"] == {"Wi-Fi": True, "Bluetooth": False}


def test_switching_radios_on_windows_passes_kind_and_state(monkeypatch):
    fake = FakeOS(monkeypatch, "windows")
    assert SystemControlTool().execute(action="wifi_off").content == "Turned Wi-Fi off."
    assert fake.calls[0]["args"] == {"kind": "WiFi", "state": "Off"}
    assert "$env:LOCUS_ARG_KIND" in fake.calls[0]["script"]
    SystemControlTool().execute(action="bluetooth_on")
    assert fake.calls[1]["args"] == {"kind": "Bluetooth", "state": "On"}


def test_switching_radios_on_linux(monkeypatch):
    fake = FakeOS(monkeypatch, "linux")
    SystemControlTool().execute(action="wifi_on")
    SystemControlTool().execute(action="bluetooth_off")
    assert fake.calls[0]["args"] == ["nmcli", "radio", "wifi", "on"]
    assert fake.calls[1]["args"] == ["rfkill", "block", "bluetooth"]


def test_mac_wifi_uses_the_wifi_device(monkeypatch):
    fake = FakeOS(
        monkeypatch,
        "macos",
        stdout=(
            "Hardware Port: Ethernet\nDevice: en1\n\n"
            "Hardware Port: Wi-Fi\nDevice: en0\n"
        ),
    )
    SystemControlTool().execute(action="wifi_off")
    assert fake.calls[-1]["args"] == ["networksetup", "-setairportpower", "en0", "off"]


def test_mac_bluetooth_needs_blueutil(monkeypatch):
    FakeOS(monkeypatch, "macos")
    monkeypatch.setattr(_os, "has_command", lambda name: False)
    result = SystemControlTool().execute(action="bluetooth_on")
    assert "blueutil" in result.content


def test_radio_failures_are_reported(monkeypatch):
    FakeOS(monkeypatch, "windows", returncode=1)
    result = SystemControlTool().execute(action="wifi_on")
    assert not result.success
    assert "Couldn't switch Wi-Fi" in result.content


@pytest.mark.parametrize(
    "action, risk",
    [("get_radios", "read"), ("wifi_off", "change"), ("bluetooth_on", "change")],
)
def test_radio_risk(action, risk):
    tool = SystemControlTool()
    assert tool_risk("system_control", tool, {"action": action}) == risk


# ── Moving, resizing and snapping windows ────────────────────────

WORK = (0, 40, 1600, 900)  # a screen with a 40 px bar on top


@pytest.mark.parametrize(
    "position, rect",
    [
        ("left", (0, 40, 800, 900)),
        ("right", (800, 40, 800, 900)),
        ("top", (0, 40, 1600, 450)),
        ("bottom", (0, 490, 1600, 450)),
        ("top_left", (0, 40, 800, 450)),
        ("bottom_right", (800, 490, 800, 450)),
        ("center", (267, 190, 1066, 600)),
    ],
)
def test_snap_rects(position, rect):
    current = (10, 50, 500, 400)
    assert (
        window_control.placement_rect("snap", {"position": position}, current, WORK)
        == rect
    )


def test_snapping_an_odd_sized_screen_covers_it():
    work = (0, 0, 1365, 767)
    left = window_control.placement_rect("snap", {"position": "left"}, work, work)
    right = window_control.placement_rect("snap", {"position": "right"}, work, work)
    assert left[2] + right[2] == 1365
    assert right[0] == left[2]


def test_moves_and_resizes_stay_on_screen():
    current = (100, 100, 600, 400)
    place = window_control.placement_rect
    assert place("move", {"x": 50, "y": 20}, current, WORK) == (50, 60, 600, 400)
    # Too far right or down: pulled back so the whole window shows.
    assert place("move", {"x": 5000, "y": 5000}, current, WORK) == (1000, 540, 600, 400)
    assert place("resize", {"width": 800, "height": 500}, current, WORK) == (
        100,
        100,
        800,
        500,
    )
    # Bigger than the screen, or tiny: limited to the screen and MIN_SIZE.
    assert place("resize", {"width": 9999, "height": 10}, current, WORK) == (
        0,
        100,
        1600,
        window_control.MIN_SIZE,
    )


@pytest.mark.parametrize(
    "params, message",
    [
        ({"action": "snap", "title": "x", "position": "middle"}, "Give a position"),
        ({"action": "move", "title": "x", "x": 10}, "Give x and y"),
        ({"action": "move", "title": "x", "x": -5, "y": 0}, "can't be negative"),
        ({"action": "resize", "title": "x", "width": "big", "height": 4}, "Give width"),
    ],
)
def test_placement_arguments_are_checked(monkeypatch, params, message):
    FakeOS(monkeypatch, "windows")
    result = WindowControlTool().execute(**params)
    assert not result.success
    assert message in result.content


def test_snapping_on_windows(monkeypatch):
    FakeOS(monkeypatch, "windows")
    placed = []
    monkeypatch.setattr(
        window_control, "list_windows", lambda: [(7, "notes.txt - Notepad")]
    )
    monkeypatch.setattr(
        window_control,
        "_windows_place",
        lambda hwnd, action, placement: (
            placed.append((hwnd, action, placement)) or True
        ),
    )

    result = WindowControlTool().execute(
        action="snap", title="notepad", position="top_right"
    )

    assert result.content == "Snapped notes.txt - Notepad to the top right."
    assert placed == [(7, "snap", {"position": "top_right"})]


def test_snapping_on_linux_uses_the_work_area(monkeypatch):
    fake = FakeOS(monkeypatch, "linux")
    outputs = {
        "-l": "0x05 0 host Editor\n",
        "-d": "0  * DG: 1920x1080  VP: 0,0  WA: 0,27 1920x1053  Workspace 1\n",
    }

    def run(args, *, env=None, input=None, timeout=0):
        fake.calls.append({"args": args})
        return _os.Completed(0, outputs.get(args[1], ""), "")

    monkeypatch.setattr(_os, "run", run)

    assert (
        WindowControlTool()
        .execute(action="snap", title="editor", position="left")
        .success
    )
    assert fake.calls[-1]["args"] == [
        "wmctrl",
        "-i",
        "-r",
        "0x05",
        "-e",
        "0,0,27,960,1053",
    ]
    WindowControlTool().execute(action="resize", title="editor", width=900, height=700)
    assert fake.calls[-1]["args"][-1] == "0,-1,-1,900,700"


def test_moving_on_macos(monkeypatch):
    fake = FakeOS(monkeypatch, "macos")

    def run(args, *, env=None, input=None, timeout=0):
        fake.calls.append({"args": args})
        script = args[2] if len(args) > 2 else ""
        if "bounds of window of desktop" in script:
            return _os.Completed(0, "0, 0, 1440, 900", "")
        if "repeat with p in" in script:
            return _os.Completed(0, "Notes\tShopping list\n", "")
        return _os.Completed(0, "", "")

    monkeypatch.setattr(_os, "run", run)

    assert (
        WindowControlTool().execute(action="move", title="shopping", x=10, y=10).success
    )
    assert fake.calls[-1]["args"][-6:] == [
        "Notes",
        "Shopping list",
        "10",
        "35",
        "-1",
        "-1",
    ]
