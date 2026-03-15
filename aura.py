"""
AURA — Autonomous Utility & Resource Assistant

Phase 1 CLI entry-point.  Starts an interactive loop that accepts
text commands, routes them through the dispatcher, prints results,
and logs every action.

Run::

    python aura.py
"""

from __future__ import annotations

import sys

from command_engine.dispatcher import dispatch
from command_engine.logger import get_logger

logger = get_logger("aura.cli")

BANNER = r"""
    ___   __  ______  ___
   /   | / / / / __ \/   |
  / /| |/ / / / /_/ / /| |
 / ___ / /_/ / _, _/ ___ |
/_/  |_\____/_/ |_/_/  |_|

Autonomous Utility & Resource Assistant
Phase 1 — Command Execution Engine
"""

HELP_TEXT = """
Available commands:

  create file <path>              Create an empty file
  delete file <path>              Delete a file
  rename file <old> <new>         Rename a file
  move file <source> <dest>       Move a file
  search files <dir> <pattern>    Search for files by glob pattern

  run command <shell_command>     Execute a shell command
  list processes                  Show top running processes
  kill process <name>             Terminate processes by name

  check system health             Check installed dev tools

  create project <name>           Scaffold a new project
  show logs <file> [lines]        Show last N lines of a log file

  help                            Show this help message
  exit / quit                     Exit AURA CLI
"""


def main() -> None:
    """Run the interactive CLI loop."""
    print(BANNER)
    logger.info("AURA CLI started")

    while True:
        try:
            user_input = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting AURA.")
            logger.info("AURA CLI terminated by user (interrupt)")
            break

        if not user_input:
            continue

        lower = user_input.lower()

        if lower in ("exit", "quit"):
            print("Goodbye.")
            logger.info("AURA CLI exited cleanly")
            break

        if lower == "help":
            print(HELP_TEXT)
            continue

        logger.info("Command received: %s", user_input)
        result = dispatch(user_input)
        print(result)
        logger.info("Result: %s", result.replace("\n", " | "))


if __name__ == "__main__":
    main()
