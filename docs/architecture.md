# AURA Architecture — Phase 1

Phase 1 is the CLI-only automation backbone. There is no voice input, no LLM reasoning, and no GUI yet — just a text-based command loop that reads a line from stdin, routes it to the correct handler, executes the action on the local filesystem or OS, logs the result, and prints a response. Every design decision in this phase is made to ensure the engine modules remain unchanged when voice, LLM, and GUI layers are added in later phases.

---

## Data Flow

```
User input (stdin)
       │
       ▼
┌──────────────────┐
│    aura.py       │  Reads a line, passes it to the dispatcher
│    (CLI REPL)    │
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│  dispatcher.py   │  Parses tokens, identifies the command verb,
│                  │  and routes to the matching handler function
└──────┬───────────┘
       │
       ├──► file_manager      (create / delete / rename / move / search)
       ├──► process_manager   (run / list / kill)
       ├──► system_check      (check system health)
       ├──► project_scaffolder(create project)
       └──► log_reader        (show logs)
              │
              │  Every handler resolves paths through path_utils
              │  before touching the filesystem
              │
              ▼
┌──────────────────┐
│   path_utils.py  │  ~ expansion, smart keywords, safety validation
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│   logger.py      │  Writes structured entry to logs/aura.log
└──────┬───────────┘
       │
       ▼
   Console output
   (result string printed to stdout)
```

---

## Module Responsibilities

### dispatcher.py

The command router. It receives a raw text string, splits it into tokens, and pattern-matches the first one or two words to decide which handler to call. It never performs any filesystem or process work itself — it only delegates. Two-path commands like `move file src dst` use a boundary-detection heuristic to split the token list into source and destination. The dispatcher is the only module that imports every handler; no handler imports another handler.

### path_utils.py

The centralized path resolution layer. Every module that touches the filesystem funnels user-supplied path strings through `resolve_path()`, which strips whitespace, expands smart-location keywords (`desktop`, `downloads`, `documents`), expands `~` via `pathlib.Path.expanduser()`, and resolves to an absolute path. It also provides `validate_not_protected()`, which blocks destructive operations on system-critical directories like `C:\Windows` or `/usr`. By centralizing this logic in one place, no individual module needs to re-implement tilde expansion or safety checks, and future modules automatically inherit the same behavior.

### file_manager.py

Provides five atomic file operations — create, delete, rename, move, and glob-search. Each function accepts a raw path string, calls `resolve_path()` to obtain an absolute `pathlib.Path`, performs the operation, and returns a human-readable result string. Delete operations additionally check `validate_not_protected()` before unlinking. Move operations auto-detect whether the destination is a directory and place the file inside it.

### process_manager.py

Wraps `subprocess.run()` for executing arbitrary shell commands and `psutil` for inspecting and terminating running processes. On Windows it passes the command string directly with `shell=True`; on Unix it splits with `shlex.split()` and avoids the shell. `list_running_processes()` returns a list of dicts sorted by memory usage. `kill_process()` terminates all processes matching a name (case-insensitive).

### system_check.py

Probes the local environment for commonly required developer tools (Python, Git, Node, Docker) by running their `--version` commands via subprocess and capturing stdout. Returns a structured dict mapping tool name to version string or `"not installed"`. It never raises — a missing tool simply produces a fallback string.

### logger.py

Configures a stdlib `logging.Logger` with two handlers: a `FileHandler` that writes every entry to `logs/aura.log` (DEBUG and above), and a `StreamHandler` for the console (WARNING and above). The format includes timestamp, level, logger name, and message. `get_logger()` is idempotent — calling it multiple times with the same name returns the same configured instance.

---

## Design Decisions

### Why pathlib over os.path

`pathlib.Path` provides an object-oriented API that makes path manipulation readable and chainable (`path.parent.mkdir(parents=True)`), handles platform differences internally, and integrates with `expanduser()`, `resolve()`, and `rglob()` without importing separate functions. `os.path` is string-based and requires composing multiple function calls for the same operations.

### Why centralized path_utils instead of per-module resolution

Before `path_utils` existed, every module called `Path(path).resolve()` independently. This meant tilde expansion, smart-keyword support, and safety checks would have to be duplicated in every function. A single `resolve_path()` entry point guarantees that every module — current and future — handles `~`, `desktop/`, and protected-path validation identically. Adding a new smart keyword or blocked directory requires changing exactly one file.

### Why stdlib logging over third-party

Phase 1 has a single external dependency (`psutil`). The stdlib `logging` module supports file handlers, formatters, log levels, and handler composition out of the box — everything AURA needs. Introducing a third-party logger (loguru, structlog) would add a dependency with no material benefit at this stage. If Phase 5's memory layer requires structured JSON logs, the handler can be swapped without changing any call site.

---

## Phase 2 Changes

- **Voice input layer** — a Whisper-based microphone listener will be added as a new input source that feeds transcribed text into the existing dispatcher, requiring zero changes to the execution modules.
- **Ollama reasoning layer** — a local LLM will sit between the input layer and the dispatcher to interpret ambiguous natural-language commands and generate structured action strings.
- **Piper TTS output layer** — a text-to-speech module will speak the result string aloud after it is printed to the console, adding a parallel output channel without modifying the handler return values.
