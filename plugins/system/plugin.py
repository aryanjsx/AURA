"""
System plugin — public entry point (worker-side).

This module is imported ONLY inside the execution worker (the isolated
subprocess).  The main process never imports ``plugins.*``.

The plugin exposes:

* :meth:`register_commands` — {action → {handler, metadata}} map whose
  handlers are name-mangled private methods on :class:`SystemExecutor`.
* :meth:`register_intents`  — empty list.  Intent parsing happens in
  the main process (:mod:`aura.intents`); the worker has no need for it.
"""

from __future__ import annotations

from typing import Any

from aura.core.event_bus import EventBus
from aura.security.permissions import PermissionLevel
from aura.core.plugin_base import IntentParser, Plugin as PluginBase

from plugins.system.executor import SystemExecutor


class Plugin(PluginBase):
    """Filesystem, process, npm, and system-monitor commands."""

    name = "system"

    def __init__(self, bus: EventBus) -> None:
        super().__init__(bus)
        self.__executor = SystemExecutor(bus)

    def register_commands(self) -> dict[str, Any]:
        handlers = self.__executor._export_executors()
        return {
            "file.create": {
                "handler": handlers["file.create"],
                "description": "Create an empty file inside the sandbox",
                "destructive": False,
                "permission_level": PermissionLevel.MEDIUM,
            },
            "file.delete": {
                "handler": handlers["file.delete"],
                "description": "Delete a file inside the sandbox",
                "destructive": True,
                "permission_level": PermissionLevel.HIGH,
            },
            "file.rename": {
                "handler": handlers["file.rename"],
                "description": "Rename a file inside the sandbox",
                "destructive": True,
                "permission_level": PermissionLevel.MEDIUM,
            },
            "file.move": {
                "handler": handlers["file.move"],
                "description": "Move a file inside the sandbox",
                "destructive": True,
                "permission_level": PermissionLevel.MEDIUM,
            },
            "file.search": {
                "handler": handlers["file.search"],
                "description": "Glob-search the sandbox",
                "destructive": False,
                "permission_level": PermissionLevel.LOW,
            },
            "process.shell": {
                "handler": handlers["process.shell"],
                "description": "Run an allowlisted shell command (argv, no shell)",
                "destructive": True,
                "permission_level": PermissionLevel.CRITICAL,
            },
            "process.list": {
                "handler": handlers["process.list"],
                "description": "List top processes by memory",
                "destructive": False,
                "permission_level": PermissionLevel.LOW,
            },
            "process.kill": {
                "handler": handlers["process.kill"],
                "description": "Terminate processes by name",
                "destructive": True,
                "permission_level": PermissionLevel.HIGH,
            },
            "system.cpu": {
                "handler": handlers["system.cpu"],
                "description": "Current CPU utilisation",
                "destructive": False,
                "permission_level": PermissionLevel.LOW,
            },
            "system.ram": {
                "handler": handlers["system.ram"],
                "description": "Current memory utilisation",
                "destructive": False,
                "permission_level": PermissionLevel.LOW,
            },
            "system.health": {
                "handler": handlers["system.health"],
                "description": "Check availability of developer tools",
                "destructive": False,
                "permission_level": PermissionLevel.LOW,
            },
            "project.create": {
                "handler": handlers["project.create"],
                "description": "Scaffold a new project directory",
                "destructive": False,
                "permission_level": PermissionLevel.MEDIUM,
            },
            "log.show": {
                "handler": handlers["log.show"],
                "description": "Show last N lines of a log file",
                "destructive": False,
                "permission_level": PermissionLevel.LOW,
            },
            "npm.install": {
                "handler": handlers["npm.install"],
                "description": "Run npm install in a sandbox directory",
                "destructive": True,
                "permission_level": PermissionLevel.HIGH,
            },
            "npm.run": {
                "handler": handlers["npm.run"],
                "description": "Run an npm script in a sandbox directory",
                "destructive": True,
                "permission_level": PermissionLevel.HIGH,
            },
        }

    def register_intents(self) -> list[IntentParser]:
        # Intent parsing lives in the main process; worker returns none.
        return []
