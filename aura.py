"""
AURA — Autonomous Utility & Resource Assistant

Phase 1 CLI entry-point.  Starts an interactive loop that accepts
text commands, routes them through the dispatcher, prints results,
and logs every action.

The loop is built on :class:`~core.io.InputSource` /
:class:`~core.io.OutputSink` abstractions so that Phase 2 can
substitute a microphone listener and TTS synthesizer without
modifying the dispatch or executor layers.

Run::

    python aura.py
    python aura.py "cpu"
    python aura.py "npm install"
"""

from __future__ import annotations

from command_engine.dispatcher import dispatch
from command_engine.logger import get_logger
from core.io import InputSource, OutputSink, StdinInput, StdoutOutput

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

  run command <shell_command>     Execute an allowed shell command (argv, no shell)
  npm install [path]              Run npm install in a project directory
  npm run <script> [path]         Run an npm script (e.g. npm run build)
  list processes                  Show top running processes
  kill process <name>             Terminate processes by name

  check system health             Check installed dev tools

  create project <name>           Scaffold a new project
  show logs <file> [lines]        Show last N lines of a log file

  help                            Show this help message
  exit / quit                     Exit AURA CLI
"""


def main(
    input_source: InputSource | None = None,
    output_sink: OutputSink | None = None,
) -> None:
    """Run the interactive CLI loop.

    Parameters
    ----------
    input_source:
        Where to read commands from.  Defaults to :class:`StdinInput`.
    output_sink:
        Where to send results.  Defaults to :class:`StdoutOutput`.
    """
    source = input_source or StdinInput()
    sink = output_sink or StdoutOutput()

    sink.send(BANNER)
    logger.info("AURA CLI started")

    while True:
        user_input = source.get_command()

        if user_input is None:
            sink.send("\nExiting AURA.")
            logger.info("AURA CLI terminated by user (interrupt)")
            break

        if not user_input:
            continue

        lower = user_input.lower()

        if lower in ("exit", "quit"):
            sink.send("Goodbye.")
            logger.info("AURA CLI exited cleanly")
            break

        if lower == "help":
            sink.send(HELP_TEXT)
            continue

        logger.info("Command received: %s", user_input)
        result = dispatch(user_input)
        sink.send(result.message)
        logger.info("Result: %s", result.message.replace("\n", " | "))


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        text = " ".join(sys.argv[1:])
        logger.info("Command received: %s", text)
        result = dispatch(text)
        print(result.message)
        sys.exit(0 if result.success else 1)
    main()
