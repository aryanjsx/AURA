# aura/executors/system_monitor.py
# AURA System Monitor — CPU, RAM, battery, disk, processes.
# Read-only operations — no safety gate needed.

from __future__ import annotations
import logging
import time
from typing import Any

from aura.schemas.command import ExecutionResult, ExecutorType

logger = logging.getLogger("aura.system_monitor")


class SystemMonitor:
    """
    Returns human-readable system stats.
    All methods return ExecutionResult — never raise to caller.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        try:
            import psutil   # verify available at init time
            self._psutil_available = True
        except ImportError:
            self._psutil_available = False
            logger.warning("psutil not installed — system monitoring unavailable.")

    def run(self, action: str, params: dict[str, Any]) -> ExecutionResult:
        ALLOWED = {
            "get_stats":          self.get_stats,
            "get_cpu":            self.get_cpu,
            "get_ram":            self.get_ram,
            "get_battery":        self.get_battery,
            "get_disk":           self.get_disk,
            "list_processes":     self.list_processes,
        }
        if action not in ALLOWED:
            return ExecutionResult(
                success=False,
                output=f"Unknown monitor action: {action}.",
                executor=ExecutorType.MONITOR,
            )
        start = time.monotonic()
        result = ALLOWED[action](params)
        result.duration_ms = int((time.monotonic() - start) * 1000)
        return result

    def get_stats(self, params: dict[str, Any]) -> ExecutionResult:
        """All stats in one call — the default AURA voice query."""
        if not self._psutil_available:
            return self._no_psutil()
        import psutil
        cpu   = psutil.cpu_percent(interval=0.5)
        ram   = psutil.virtual_memory()
        batt  = psutil.sensors_battery()
        batt_str = ""
        if batt:
            status = "charging" if batt.power_plugged else "on battery"
            batt_str = f", battery at {batt.percent:.0f} percent {status}"
        output = (
            f"CPU is at {cpu:.0f} percent, "
            f"RAM is at {ram.percent:.0f} percent "
            f"({ram.used // (1024**3):.1f} of {ram.total // (1024**3):.1f} gigabytes used)"
            f"{batt_str}."
        )
        return ExecutionResult(
            success=True, output=output,
            data={"cpu": cpu, "ram_percent": ram.percent, "battery": batt.percent if batt else None},
            executor=ExecutorType.MONITOR,
        )

    def get_cpu(self, params: dict[str, Any]) -> ExecutionResult:
        if not self._psutil_available:
            return self._no_psutil()
        import psutil
        cpu = psutil.cpu_percent(interval=0.5)
        return ExecutionResult(
            success=True, output=f"CPU usage is {cpu:.0f} percent.",
            data={"cpu": cpu}, executor=ExecutorType.MONITOR,
        )

    def get_ram(self, params: dict[str, Any]) -> ExecutionResult:
        if not self._psutil_available:
            return self._no_psutil()
        import psutil
        ram = psutil.virtual_memory()
        return ExecutionResult(
            success=True,
            output=(
                f"RAM usage is {ram.percent:.0f} percent. "
                f"{ram.available // (1024**2):.0f} megabytes available."
            ),
            data={"ram_percent": ram.percent, "available_mb": ram.available // (1024**2)},
            executor=ExecutorType.MONITOR,
        )

    def get_battery(self, params: dict[str, Any]) -> ExecutionResult:
        if not self._psutil_available:
            return self._no_psutil()
        import psutil
        batt = psutil.sensors_battery()
        if batt is None:
            return ExecutionResult(
                success=True,
                output="No battery detected — this appears to be a desktop.",
                executor=ExecutorType.MONITOR,
            )
        status = "charging" if batt.power_plugged else "discharging"
        return ExecutionResult(
            success=True,
            output=f"Battery is at {batt.percent:.0f} percent and {status}.",
            data={"percent": batt.percent, "plugged": batt.power_plugged},
            executor=ExecutorType.MONITOR,
        )

    def get_disk(self, params: dict[str, Any]) -> ExecutionResult:
        if not self._psutil_available:
            return self._no_psutil()
        import psutil
        path = params.get("path", "/")
        try:
            disk = psutil.disk_usage(path)
            free_gb = disk.free / (1024 ** 3)
            total_gb = disk.total / (1024 ** 3)
            return ExecutionResult(
                success=True,
                output=(
                    f"Disk usage is {disk.percent:.0f} percent. "
                    f"{free_gb:.1f} gigabytes free of {total_gb:.1f} total."
                ),
                data={"percent": disk.percent, "free_gb": round(free_gb, 1)},
                executor=ExecutorType.MONITOR,
            )
        except FileNotFoundError:
            return ExecutionResult(
                success=False,
                output=f"Couldn't find disk at {path}.",
                executor=ExecutorType.MONITOR,
            )

    def list_processes(self, params: dict[str, Any]) -> ExecutionResult:
        if not self._psutil_available:
            return self._no_psutil()
        import psutil
        limit = int(params.get("limit", 10))
        procs = sorted(
            psutil.process_iter(["name", "cpu_percent", "memory_percent"]),
            key=lambda p: p.info["cpu_percent"] or 0,
            reverse=True,
        )[:limit]
        names = [p.info["name"] for p in procs]
        output = f"Top {len(names)} processes by CPU: {', '.join(names)}."
        return ExecutionResult(
            success=True, output=output,
            data={"processes": [p.info for p in procs]},
            executor=ExecutorType.MONITOR,
        )

    def _no_psutil(self) -> ExecutionResult:
        return ExecutionResult(
            success=False,
            output="System monitoring requires psutil. Run: pip install psutil.",
            error="psutil not installed",
            executor=ExecutorType.MONITOR,
        )
