"""
System plugin — text-to-intent parsers.

Private module.  Parsers are a list of callables that each accept the
raw command string and return either an :class:`Intent` or ``None``.
The router runs them in order; the first non-``None`` wins.
"""

from __future__ import annotations

import re
import shlex

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


# --------------------------------------------------------------------------
# Canonical action-id parser (fallback, ordered last in the parser chain).
#
# Accepts input shaped like one of:
#
#     system.cpu
#     system.ram
#     file.create path=foo.txt
#     file.search directory=. pattern=*.py limit=50
#     process.shell command="git status"
#
# The dotted head must look like a real action identifier.  Additional
# tokens are parsed as ``key=value`` pairs via :func:`shlex.split`, which
# preserves quoted values without executing anything.
#
# Security note
# -------------
# This parser produces an :class:`Intent` only; it performs NO dispatch,
# NO filesystem I/O, and NO subprocess work.  Every resulting intent is
# still handed to :meth:`CommandRegistry.execute` which runs the full
# safety pipeline (rate limit -> permission validator -> param schema
# -> safety gate -> worker).  Destructive actions have ``requires_confirm``
# forced to ``True`` inside the registry regardless of what is set here,
# so this parser cannot bypass the safety gate.
# --------------------------------------------------------------------------

# Matches ``plugin.action`` or ``plugin.sub.action``; each segment must
# start with an ASCII letter and contain only lowercase ASCII / digits /
# underscores.  The strict shape makes it impossible for arbitrary user
# text to be silently funneled into the registry as an action name.
_ACTION_ID_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")

# Integer parameter names allowed by the current schema.  We coerce
# ``key=value`` strings to ``int`` for exactly these names so that e.g.
# ``file.search directory=. pattern=*.py limit=50`` passes the int-typed
# ``limit`` spec in :mod:`aura.core.param_schema`.  Anything else stays a
# string -- no implicit coercion, no silent ``bool``/``float``/container.
_INT_PARAM_NAMES: frozenset[str] = frozenset({"limit"})

# Actions that the registry marks destructive at manifest level.  We set
# ``requires_confirm=True`` up front so the Router -> Registry hand-off
# is explicit; the Registry would force it anyway (see
# ``_apply_safety_inline`` in ``aura/runtime/command_registry.py``), this
# is belt-and-braces for clarity in logs and tests.
_DESTRUCTIVE_ACTIONS: frozenset[str] = frozenset({
    "file.delete",
    "file.rename",
    "file.move",
    "process.shell",
    "process.kill",
    "npm.install",
    "npm.run",
})


def _looks_like_action_id(token: str) -> bool:
    return bool(_ACTION_ID_RE.fullmatch(token))


def parse_action_id(text: str) -> Intent | None:
    """Fallback parser: recognise canonical ``plugin.action`` ids.

    Returns ``None`` (so later parsers / the router's ``Unknown command``
    error take over) for anything that does not look like an action id.
    Never raises.
    """
    stripped = (text or "").strip()
    if not stripped:
        return None

    # shlex handles quoted values ("command=\"git status\"") without any
    # shell execution. posix=True gives consistent behaviour on Windows.
    try:
        tokens = shlex.split(stripped, posix=True)
    except ValueError:
        # Unbalanced quotes etc. -- let another parser try, or fall
        # through to the router's Unknown-command path.
        return None

    if not tokens:
        return None

    head = tokens[0]
    if not _looks_like_action_id(head):
        return None

    args: dict[str, object] = {}
    for tok in tokens[1:]:
        if "=" not in tok:
            # Positional args are ambiguous across actions with multiple
            # required params; require explicit key=value for safety.
            return None
        key, _, value = tok.partition("=")
        key = key.strip()
        if not key or not re.fullmatch(r"[a-z_][a-z0-9_]*", key):
            return None
        if key in args:
            # Duplicate keys would silently win one over the other;
            # refuse so the user can see the problem.
            return None
        if key in _INT_PARAM_NAMES:
            try:
                args[key] = int(value)
            except ValueError:
                return None
        else:
            args[key] = value

    # We deliberately do NOT filter unknown keys here.  The registry's
    # ``validate_params`` will reject them with a message that includes
    # the full action signature ("Usage: file.create path=<str>"),
    # which is strictly more helpful than a bare "Unknown command".
    # If the action is not in PARAM_SCHEMAS either, the registry raises
    # a clear "Unknown action" error.

    return Intent(
        action=head,
        args=args,
        raw_text=text,
        requires_confirm=head in _DESTRUCTIVE_ACTIONS,
    )


__all__: list[str] = []
