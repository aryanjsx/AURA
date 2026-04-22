"""
System plugin — text-to-intent parsers.

Private module.  Parsers are a list of callables that each accept the
raw command string and return either an :class:`Intent` or ``None``.
The router runs them in order; the first non-``None`` wins.
"""

from __future__ import annotations

from aura.core.intent import Intent

_CPU_PHRASES: frozenset[str] = frozenset({
    "cpu", "cpu usage", "get cpu", "get cpu usage",
    "what is cpu usage", "show cpu usage",
})
_RAM_PHRASES: frozenset[str] = frozenset({
    "ram", "memory", "ram usage", "memory usage",
    "get ram", "get memory", "show memory", "show ram",
})
_PROCESS_PHRASES: frozenset[str] = frozenset({
    "processes", "show processes", "list processes", "running processes",
})
_HEALTH_PHRASES: frozenset[str] = frozenset({
    "check system health", "system health", "health check",
})


def _normalise(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _tokens(text: str) -> list[str]:
    return text.strip().split()


def _rest(tokens: list[str], start: int) -> str:
    return " ".join(tokens[start:]).strip()


def parse_system_monitor(text: str) -> Intent | None:
    norm = _normalise(text)
    if norm in _CPU_PHRASES:
        return Intent(action="system.cpu", args={}, raw_text=text)
    if norm in _RAM_PHRASES:
        return Intent(action="system.ram", args={}, raw_text=text)
    if norm in _PROCESS_PHRASES:
        return Intent(action="process.list", args={}, raw_text=text)
    if norm in _HEALTH_PHRASES:
        return Intent(action="system.health", args={}, raw_text=text)
    return None


def parse_file_commands(text: str) -> Intent | None:
    tokens = _tokens(text)
    if len(tokens) < 2:
        return None
    head = tokens[0].lower()
    sub = tokens[1].lower()

    if head == "create" and sub == "file":
        path = _rest(tokens, 2)
        if not path:
            return None
        return Intent(
            action="file.create", args={"path": path}, raw_text=text,
            requires_confirm=False,
        )

    if head == "delete" and sub == "file":
        path = _rest(tokens, 2)
        if not path:
            return None
        return Intent(
            action="file.delete", args={"path": path}, raw_text=text,
            requires_confirm=True,
        )

    if head == "rename" and sub == "file" and len(tokens) >= 4:
        new_name = tokens[-1]
        old_path = " ".join(tokens[2:-1]).strip()
        if not old_path:
            return None
        return Intent(
            action="file.rename",
            args={"old_name": old_path, "new_name": new_name},
            raw_text=text,
        )

    if head == "move" and sub == "file" and len(tokens) >= 4:
        mid = len(tokens) // 2 + 1
        source = " ".join(tokens[2:mid]).strip()
        destination = " ".join(tokens[mid:]).strip()
        if not source or not destination:
            return None
        return Intent(
            action="file.move",
            args={"source": source, "destination": destination},
            raw_text=text,
        )

    if head == "search" and sub == "files" and len(tokens) >= 4:
        pattern = tokens[-1]
        directory = " ".join(tokens[2:-1]).strip()
        if not directory:
            return None
        return Intent(
            action="file.search",
            args={"directory": directory, "pattern": pattern},
            raw_text=text,
        )

    return None


def parse_process_commands(text: str) -> Intent | None:
    tokens = _tokens(text)
    if len(tokens) < 2:
        return None
    head = tokens[0].lower()
    sub = tokens[1].lower()

    if head == "run" and sub == "command":
        cmd = _rest(tokens, 2)
        if not cmd:
            return None
        return Intent(
            action="process.shell", args={"command": cmd}, raw_text=text,
            requires_confirm=True,
        )

    if head == "kill" and sub == "process":
        name = _rest(tokens, 2)
        if not name:
            return None
        return Intent(
            action="process.kill", args={"process_name": name},
            raw_text=text, requires_confirm=True,
        )

    return None


def parse_npm_commands(text: str) -> Intent | None:
    tokens = _tokens(text)
    if not tokens or tokens[0].lower() != "npm":
        return None
    if len(tokens) < 2:
        return None
    sub = tokens[1].lower()

    if sub == "install":
        cwd = _rest(tokens, 2) or "."
        return Intent(
            action="npm.install", args={"cwd": cwd}, raw_text=text,
        )

    if sub == "run" and len(tokens) >= 3:
        script = tokens[2]
        cwd = _rest(tokens, 3) or "."
        return Intent(
            action="npm.run", args={"script": script, "cwd": cwd},
            raw_text=text,
        )

    return None


__all__: list[str] = []
