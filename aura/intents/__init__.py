"""
AURA — Intent parsers (main-process only).

Intent parsers are pure text-to-:class:`~aura.core.intent.Intent` functions.
They live in the main process (alongside the Router) and are never loaded
into the execution worker, which runs no user-facing text parsing.
"""

from __future__ import annotations

from aura.core.plugin_base import IntentParser
from aura.intents.system_intents import (
    parse_action_id,
    parse_file_commands,
    parse_npm_commands,
    parse_process_commands,
    parse_system_monitor,
)


def default_intent_parsers() -> list[IntentParser]:
    # parse_action_id is ordered LAST so natural-language phrases always
    # win.  It only matches strictly-shaped ``plugin.action`` ids and is
    # a pure text parser -- every resulting intent still runs through the
    # full CommandRegistry safety pipeline.
    return [
        parse_system_monitor,
        parse_file_commands,
        parse_process_commands,
        parse_npm_commands,
        parse_action_id,
    ]


__all__ = [
    "default_intent_parsers",
    "parse_action_id",
    "parse_file_commands",
    "parse_npm_commands",
    "parse_process_commands",
    "parse_system_monitor",
]
