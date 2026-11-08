"""Volume, mute, screen brightness, dark mode and locking the screen."""

from __future__ import annotations

import re
from typing import Any, Optional

from locus.core.registry import ToolRegistry
from locus.core.types import ToolResult
from locus.tools._stubs import BaseTool, ToolSpec
from locus.tools.desktop import _os

ACTIONS = (
    "get_volume",
    "set_volume",
    "mute",
    "unmute",
    "set_brightness",
    "dark_mode",
    "light_mode",
    "lock_screen",
    "get_radios",
    "wifi_on",
    "wifi_off",
    "bluetooth_on",
    "bluetooth_off",
)

#: action -> (radio, turn on?)
_RADIO_ACTIONS = {
    "wifi_on": ("wifi", True),
    "wifi_off": ("wifi", False),
    "bluetooth_on": ("bluetooth", True),
    "bluetooth_off": ("bluetooth", False),
}

# Core Audio's endpoint volume for the default output device. The method
# order in each interface must match the COM vtable, hence the placeholders.
_WIN_AUDIO = """Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
[Guid("5CDF2C82-841E-4546-9722-0CF74078229A"),
 InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IAudioEndpointVolume {
  int f(); int g(); int h(); int i();
  int SetMasterVolumeLevelScalar(float fLevel, Guid pguidEventContext);
  int j();
  int GetMasterVolumeLevelScalar(out float pfLevel);
  int k(); int l(); int m(); int n();
  int SetMute([MarshalAs(UnmanagedType.Bool)] bool bMute, Guid pguidEventContext);
  int GetMute(out bool pbMute);
}
[Guid("D666063F-1587-4E43-81F1-B948E807363F"),
 InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDevice {
  int Activate(ref Guid id, int clsCtx, int activationParams,
               out IAudioEndpointVolume aev);
}
[Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"),
 InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDeviceEnumerator {
  int f();
  int GetDefaultAudioEndpoint(int dataFlow, int role, out IMMDevice endpoint);
}
[ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")]
class MMDeviceEnumeratorComObject { }
public class LocusAudio {
  static IAudioEndpointVolume Endpoint() {
    var devices = new MMDeviceEnumeratorComObject() as IMMDeviceEnumerator;
    IMMDevice device;
    Marshal.ThrowExceptionForHR(devices.GetDefaultAudioEndpoint(0, 1, out device));
    IAudioEndpointVolume volume;
    var id = typeof(IAudioEndpointVolume).GUID;
    Marshal.ThrowExceptionForHR(device.Activate(ref id, 23, 0, out volume));
    return volume;
  }
  public static float Volume {
    get {
      float v;
      Marshal.ThrowExceptionForHR(Endpoint().GetMasterVolumeLevelScalar(out v));
      return v;
    }
    set {
      Marshal.ThrowExceptionForHR(
        Endpoint().SetMasterVolumeLevelScalar(value, Guid.Empty));
    }
  }
  public static bool Mute {
    get { bool m; Marshal.ThrowExceptionForHR(Endpoint().GetMute(out m)); return m; }
    set { Marshal.ThrowExceptionForHR(Endpoint().SetMute(value, Guid.Empty)); }
  }
}
'@
"""
_WIN_GET_VOLUME = _WIN_AUDIO + (
    "'{0} {1}' -f [Math]::Round([LocusAudio]::Volume * 100), [LocusAudio]::Mute"
)
_WIN_SET_VOLUME = _WIN_AUDIO + (
    "[LocusAudio]::Mute = $false; "
    "[LocusAudio]::Volume = [float]$env:LOCUS_ARG_LEVEL / 100"
)
_WIN_SET_MUTE = _WIN_AUDIO + "[LocusAudio]::Mute = [bool][int]$env:LOCUS_ARG_MUTE"
_WIN_SET_BRIGHTNESS = (
    "Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods"
    " -ErrorAction Stop | Invoke-CimMethod -MethodName WmiSetBrightness"
    " -Arguments @{Timeout = 1; Brightness = [byte]$env:LOCUS_ARG_LEVEL}"
    " | Out-Null"
)
_WIN_PERSONALIZE = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"

# Windows.Devices.Radios switches Wi-Fi and Bluetooth without admin rights.
# PowerShell 5.1 waits on its async calls through WindowsRuntime's AsTask.
_WIN_RADIOS = """Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
  $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
  $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } |
  Select-Object -First 1
function Await($op, [Type]$type) {
  $t = $asTask.MakeGenericMethod($type).Invoke($null, @($op))
  $t.Wait(-1) | Out-Null
  $t.Result
}
[Windows.Devices.Radios.Radio, Windows.System.Devices, ContentType = WindowsRuntime] |
  Out-Null
$listType = [System.Collections.Generic.IReadOnlyList[Windows.Devices.Radios.Radio]]
$radios = Await ([Windows.Devices.Radios.Radio]::GetRadiosAsync()) $listType
"""
_WIN_GET_RADIOS = (
    _WIN_RADIOS + "$radios | ForEach-Object { '{0} {1}' -f $_.Kind, $_.State }"
)
_WIN_SET_RADIO = (
    _WIN_RADIOS
    + """$status = [Windows.Devices.Radios.RadioAccessStatus]
$access = Await ([Windows.Devices.Radios.Radio]::RequestAccessAsync()) $status
if ($access -ne 'Allowed') { throw "Windows didn't allow it ($access)." }
$radio = $radios | Where-Object { $_.Kind -eq $env:LOCUS_ARG_KIND } |
  Select-Object -First 1
if (-not $radio) { throw "This computer has no $env:LOCUS_ARG_KIND radio." }
$state = [Windows.Devices.Radios.RadioState]$env:LOCUS_ARG_STATE
$result = Await ($radio.SetStateAsync($state)) $status
if ($result -ne 'Allowed') { throw "Windows didn't change it ($result)." }
"""
)


def _level(raw: object) -> Optional[int]:
    try:
        level = int(round(float(raw)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return level if 0 <= level <= 100 else None


def _windows_dark_mode(dark: bool) -> None:
    import ctypes
    import winreg

    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, _WIN_PERSONALIZE, 0, winreg.KEY_SET_VALUE
    ) as key:
        for name in ("AppsUseLightTheme", "SystemUsesLightTheme"):
            winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, 0 if dark else 1)
    # Tell open windows the theme changed (HWND_BROADCAST, WM_SETTINGCHANGE).
    result = ctypes.c_ulong()
    ctypes.windll.user32.SendMessageTimeoutW(  # type: ignore[attr-defined]
        0xFFFF, 0x001A, 0, "ImmersiveColorSet", 0x0002, 2000, ctypes.byref(result)
    )


@ToolRegistry.register("system_control")
class SystemControlTool(BaseTool):
    """Change everyday system settings on the user's computer."""

    tool_id = "system_control"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="system_control",
            description=(
                "Everyday computer settings. 'get_volume' reads the speaker"
                " volume (0-100) and whether it's muted. 'set_volume' sets it"
                " to 'level' (0-100) and unmutes. 'mute' and 'unmute' the"
                " speakers. 'set_brightness' sets a laptop screen to 'level'"
                " (0-100). 'dark_mode' and 'light_mode' switch the theme."
                " 'lock_screen' locks the computer. 'get_radios' reports"
                " whether Wi-Fi and Bluetooth are on; 'wifi_on', 'wifi_off',"
                " 'bluetooth_on' and 'bluetooth_off' switch them."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": list(ACTIONS)},
                    "level": {
                        "type": "number",
                        "description": "0-100, for set_volume and set_brightness.",
                    },
                },
                "required": ["action"],
            },
            category="desktop",
        )

    def risk_for(self, arguments: dict) -> str:
        read_only = ("get_volume", "get_radios")
        return "read" if arguments.get("action") in read_only else "change"

    def execute(self, **params: Any) -> ToolResult:
        action = params.get("action")
        if action not in ACTIONS:
            return _os.bad_action("system_control", action, ACTIONS)
        level = _level(params.get("level"))
        if action in ("set_volume", "set_brightness") and level is None:
            return _os.fail("system_control", "Give a level from 0 to 100.")
        if action == "get_radios" or action in _RADIO_ACTIONS:
            return self._radios(action)
        handler = {
            "windows": self._windows,
            "macos": self._macos,
            "linux": self._linux,
        }.get(_os.system())
        if handler is None:
            return _os.unsupported("system_control", "Changing settings")
        return handler(action, level)

    # ── Windows ──────────────────────────────────────────────────

    def _windows(self, action: str, level: Optional[int]) -> ToolResult:
        if action == "lock_screen":
            import ctypes

            if not ctypes.windll.user32.LockWorkStation():  # type: ignore[attr-defined]
                return _os.fail("system_control", "Windows didn't lock the screen.")
            return _os.ok("system_control", "Locked the screen.")
        if action in ("dark_mode", "light_mode"):
            try:
                _windows_dark_mode(action == "dark_mode")
            except OSError as exc:
                return _os.fail("system_control", f"Couldn't change the theme: {exc}")
            return _os.ok("system_control", f"Switched to {action.replace('_', ' ')}.")
        if action == "get_volume":
            done = _os.powershell(_WIN_GET_VOLUME)
            if not done.ok:
                return _os.fail(
                    "system_control", f"Couldn't read the volume: {done.error()}"
                )
            volume, muted = done.stdout.split()
            return self._volume_result(int(volume), muted.lower() == "true")
        if action == "set_volume":
            done = _os.powershell(_WIN_SET_VOLUME, args={"level": level})
        elif action in ("mute", "unmute"):
            done = _os.powershell(_WIN_SET_MUTE, args={"mute": int(action == "mute")})
        else:  # set_brightness
            done = _os.powershell(_WIN_SET_BRIGHTNESS, args={"level": level})
            if not done.ok:
                return _os.fail(
                    "system_control",
                    "Couldn't set the brightness. Windows can only change it"
                    " on built-in laptop screens.",
                )
        if not done.ok:
            return _os.fail(
                "system_control", f"Couldn't change the volume: {done.error()}"
            )
        return self._done(action, level)

    # ── macOS ────────────────────────────────────────────────────

    def _macos(self, action: str, level: Optional[int]) -> ToolResult:
        scripts = {
            "get_volume": 'get (output volume of (get volume settings)) & " " & '
            "(output muted of (get volume settings))",
            "set_volume": f"set volume output volume {level} without output muted",
            "mute": "set volume with output muted",
            "unmute": "set volume without output muted",
            "dark_mode": 'tell application "System Events" to tell appearance '
            "preferences to set dark mode to true",
            "light_mode": 'tell application "System Events" to tell appearance '
            "preferences to set dark mode to false",
        }
        if action == "lock_screen":
            done = _os.run(["pmset", "displaysleepnow"])
        elif action in scripts:
            done = _os.run(["osascript", "-e", scripts[action]])
        else:
            return _os.unsupported("system_control", "Changing the brightness")
        if not done.ok:
            return _os.fail("system_control", f"That didn't work: {done.error()}")
        if action == "get_volume":
            volume, muted = done.stdout.split()
            return self._volume_result(int(volume), muted == "true")
        return self._done(action, level)

    # ── Linux (PulseAudio or PipeWire, systemd) ──────────────────

    def _linux(self, action: str, level: Optional[int]) -> ToolResult:
        sink = "@DEFAULT_SINK@"
        if action == "lock_screen":
            done = _os.run(["loginctl", "lock-session"])
        elif action == "get_volume":
            done = _os.run(["pactl", "get-sink-volume", sink])
            muted = _os.run(["pactl", "get-sink-mute", sink])
            match = re.search(r"(\d+)%", done.stdout)
            if not done.ok or not match:
                return _os.fail(
                    "system_control", f"Couldn't read the volume: {done.error()}"
                )
            return self._volume_result(int(match.group(1)), "yes" in muted.stdout)
        elif action == "set_volume":
            _os.run(["pactl", "set-sink-mute", sink, "0"])
            done = _os.run(["pactl", "set-sink-volume", sink, f"{level}%"])
        elif action in ("mute", "unmute"):
            done = _os.run(
                ["pactl", "set-sink-mute", sink, "1" if action == "mute" else "0"]
            )
        else:
            return _os.unsupported(
                "system_control", action.replace("_", " ").capitalize()
            )
        if not done.ok:
            return _os.fail("system_control", f"That didn't work: {done.error()}")
        return self._done(action, level)

    # ── Wi-Fi and Bluetooth ──────────────────────────────────────

    def _radios(self, action: str) -> ToolResult:
        os_name = _os.system()
        if action == "get_radios":
            states = {
                "windows": self._windows_radio_states,
                "macos": self._macos_radio_states,
                "linux": self._linux_radio_states,
            }.get(os_name)
            if states is None:
                return _os.unsupported("system_control", "Wi-Fi and Bluetooth")
            found = states()
            if isinstance(found, ToolResult):
                return found
            text = "; ".join(
                f"{name}: {'on' if on else 'off'}" for name, on in found.items()
            )
            return _os.ok(
                "system_control", text or "No Wi-Fi or Bluetooth found.", radios=found
            )

        radio, on = _RADIO_ACTIONS[action]
        label = "Wi-Fi" if radio == "wifi" else "Bluetooth"
        if os_name == "windows":
            done = _os.powershell(
                _WIN_SET_RADIO,
                args={
                    "kind": "WiFi" if radio == "wifi" else "Bluetooth",
                    "state": "On" if on else "Off",
                },
                timeout=40,
            )
        elif os_name == "macos":
            if radio == "wifi":
                device = self._macos_wifi_device()
                if device is None:
                    return _os.fail("system_control", "This Mac has no Wi-Fi.")
                done = _os.run(
                    ["networksetup", "-setairportpower", device, "on" if on else "off"]
                )
            elif _os.has_command("blueutil"):
                done = _os.run(["blueutil", "--power", "1" if on else "0"])
            else:
                return _os.fail(
                    "system_control", "Install blueutil to switch Bluetooth on a Mac."
                )
        elif os_name == "linux":
            if radio == "wifi":
                done = _os.run(["nmcli", "radio", "wifi", "on" if on else "off"])
            else:
                done = _os.run(["rfkill", "unblock" if on else "block", "bluetooth"])
        else:
            return _os.unsupported("system_control", "Wi-Fi and Bluetooth")
        if not done.ok:
            return _os.fail(
                "system_control", f"Couldn't switch {label}: {done.error()}"
            )
        return _os.ok("system_control", f"Turned {label} {'on' if on else 'off'}.")

    @staticmethod
    def _windows_radio_states():
        done = _os.powershell(_WIN_GET_RADIOS, timeout=40)
        if not done.ok:
            return _os.fail(
                "system_control", f"Couldn't read Wi-Fi and Bluetooth: {done.error()}"
            )
        names = {"wifi": "Wi-Fi", "bluetooth": "Bluetooth"}
        found = {}
        for line in done.stdout.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[0].lower() in names:
                found[names[parts[0].lower()]] = parts[1].lower() == "on"
        return found

    @staticmethod
    def _macos_wifi_device() -> Optional[str]:
        done = _os.run(["networksetup", "-listallhardwareports"])
        match = re.search(
            r"Hardware Port: (?:Wi-Fi|AirPort)\s*\nDevice: (\S+)", done.stdout
        )
        return match.group(1) if match else None

    def _macos_radio_states(self):
        found = {}
        device = self._macos_wifi_device()
        if device:
            done = _os.run(["networksetup", "-getairportpower", device])
            found["Wi-Fi"] = done.stdout.strip().lower().endswith("on")
        if _os.has_command("blueutil"):
            done = _os.run(["blueutil", "--power"])
            found["Bluetooth"] = done.stdout.strip() == "1"
        return found

    @staticmethod
    def _linux_radio_states():
        found = {}
        wifi = _os.run(["nmcli", "radio", "wifi"])
        if wifi.ok:
            found["Wi-Fi"] = wifi.stdout.strip() == "enabled"
        bluetooth = _os.run(["rfkill", "list", "bluetooth"])
        if bluetooth.ok and bluetooth.stdout.strip():
            found["Bluetooth"] = "Soft blocked: yes" not in bluetooth.stdout
        return found

    # ── Results ──────────────────────────────────────────────────

    @staticmethod
    def _volume_result(volume: int, muted: bool) -> ToolResult:
        text = f"Volume is {volume}%" + (" and muted." if muted else ".")
        return _os.ok("system_control", text, volume=volume, muted=muted)

    @staticmethod
    def _done(action: str, level: Optional[int]) -> ToolResult:
        text = {
            "set_volume": f"Set the volume to {level}%.",
            "mute": "Muted the speakers.",
            "unmute": "Unmuted the speakers.",
            "set_brightness": f"Set the brightness to {level}%.",
            "dark_mode": "Switched to dark mode.",
            "light_mode": "Switched to light mode.",
            "lock_screen": "Locked the screen.",
        }[action]
        return _os.ok("system_control", text)


__all__ = ["SystemControlTool"]
