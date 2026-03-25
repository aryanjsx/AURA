# AURA Architecture

AURA's architecture is designed so that the command execution layer remains untouched as new input channels (voice), reasoning engines (LLM), and output channels (TTS, GUI) are added. Phase 1 built the execution backbone and CLI. The Phase 2 preparation added an intent layer, command registry, policy gate, and LLM backend abstraction — all in place and working, waiting for a real Whisper listener and Ollama model to complete the pipeline.

---

## Data Flow

### Phase 1 — CLI (current)

```
User input (stdin)
       │
       ▼
┌──────────────────┐
│    aura.py       │  Reads input via InputSource abstraction
│    (CLI REPL)    │
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│  dispatcher.py   │  parse_intent() converts text → Intent
│                  │  execute_intent() routes Intent → handler
└──────┬───────────┘
       │  ┌──────────────┐
       │  │  policy.py   │  Validates intent before execution
       │  └──────────────┘
       │
       ├──► file_manager      (create / delete / rename / move / search)
       ├──► process_manager   (run / list / kill)
       ├──► system_check      (check system health)
       ├──► project_scaffolder (create project)
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
   (result string printed via OutputSink)
```

### Phase 2 — Voice + LLM (planned)

```
Microphone input
       │
       ▼
┌──────────────────┐
│  Whisper STT     │  Transcribes audio → text
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│  LLMBrain        │  Sends text to Ollama → structured Intent
│  + OllamaBackend │  Uses command registry for prompt context
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ execute_intent() │  Same pipeline as CLI — no changes needed
│  + policy.py     │
└──────┬───────────┘
       │
       ▼
   CommandResult
       │
       ├──► Console output
       └──► Piper TTS (speak result aloud)
```

---

## Module Responsibilities

### core/intent.py

The `Intent` dataclass represents a parsed user intention — the bridge between raw text (or LLM output) and the execution layer. It carries an `action` string (e.g. `"file.create"`), a dict of `args` that map to handler parameter names, the `raw_text` that produced it, the `source` channel (`"cli"`, `"llm"`, `"voice"`), and a `confidence` score. The Intent is frozen (immutable after creation) and serves as the single contract between input parsing and command execution.

### core/policy.py

The `CommandPolicy` class is the centralized safety gate. Every intent passes through `validate_intent()` before a handler is invoked — both in the CLI dispatcher and (in Phase 2) in the LLM pipeline. Shell commands are checked against a blocked-pattern list (exact matches and substring patterns). File-path safety is handled separately by `path_utils.validate_not_protected()`. The policy is the single source of truth for command safety; `process_manager` delegates to it rather than maintaining its own checks.

### core/context.py

The `AppContext` dataclass bundles cross-cutting concerns — config, policy, and session state — into a single injectable object. Phase 2 will add the LLM backend and conversation history here so that components receive one object instead of importing scattered globals.

### core/backends/

The LLM backend abstraction layer. `base.py` defines the `LLMBackend` ABC with `complete()` and `is_available()` methods. `ollama_backend.py` provides a stub that returns canned responses so the pipeline can be tested end-to-end before a real Ollama server is connected. `factory.py` reads config and returns the appropriate backend instance.

### core/config_loader.py

Loads settings from `config.yaml` (user-local, gitignored) with fallback to `config.example.yaml` (tracked template). Supports dot-notation access (`get("logging.level")`), deep-merges user overrides into built-in defaults, and caches the result. Every other module reads settings through this loader.

### core/io.py

Defines `InputSource` and `OutputSink` abstract base classes so that the main loop can read commands and emit results through any channel. Phase 1 provides `StdinInput` and `StdoutOutput`. Phase 2 will add a Whisper-based input source and a Piper TTS output sink — the dispatcher and handlers require zero changes.

### core/result.py

The `CommandResult` dataclass is the uniform return type for every handler. It carries `success` (bool), `message` (human-readable text), `data` (optional structured payload for programmatic consumers), and `command_type` (dot-namespaced label like `"file.create"`).

### dispatcher.py

The command router. `parse_intent()` converts raw text into a structured `Intent` using keyword matching. `execute_intent()` looks up the handler in `COMMAND_REGISTRY` (a dict mapping action strings like `"file.create"` to handler functions), validates via the policy gate, and calls the handler with `**intent.args`. The original `dispatch(command)` function is preserved as the backward-compatible entry point — it calls `parse_intent()` then `execute_intent()` internally. `get_available_commands()` returns metadata for every registered command, enabling LLM prompt generation and dynamic help text.

### path_utils.py

The centralized path resolution layer. Every module that touches the filesystem funnels user-supplied path strings through `resolve_path()`, which strips whitespace, expands smart-location keywords (`desktop`, `downloads`, `documents`), expands `~` via `pathlib.Path.expanduser()`, and resolves to an absolute path. It also provides `validate_not_protected()`, which blocks destructive operations on system-critical directories like `C:\Windows` or `/usr`. Adding a new smart keyword or blocked directory requires changing exactly one file.

### file_manager.py

Provides five atomic file operations — create, delete, rename, move, and glob-search. Each function accepts a raw path string, calls `resolve_path()` to obtain an absolute `pathlib.Path`, performs the operation, and returns a `CommandResult`. Delete operations additionally check `validate_not_protected()` before unlinking. Move operations auto-detect whether the destination is a directory and place the file inside it.

### process_manager.py

Wraps `subprocess.run()` for executing arbitrary shell commands and `psutil` for inspecting and terminating running processes. Commands are validated through `CommandPolicy` before execution. On Windows it passes the command string directly with `shell=True`; on Unix it splits with `shlex.split()` and avoids the shell.

### system_check.py

Probes the local environment for commonly required developer tools (Python, Git, Node, Docker) by running their `--version` commands via subprocess and capturing stdout. Returns a structured dict mapping tool name to version string or `"not installed"`. The tool list is loaded from config.

### logger.py

Configures a stdlib `logging.Logger` with two handlers: a `RotatingFileHandler` that writes every entry to `logs/aura.log` with automatic rotation, and a `StreamHandler` for the console (WARNING and above). `get_logger()` is idempotent — calling it multiple times with the same name returns the same configured instance.

### core/llm_brain.py

The `LLMBrain` class accepts natural-language text and returns a structured `Intent`. It wraps an `LLMBackend` and will (in Phase 2) build a prompt from the command registry, send it to the model, and parse the structured response. Currently a stub that returns a low-confidence passthrough intent when the backend is unavailable.

---

## Design Decisions

### Why pathlib over os.path

`pathlib.Path` provides an object-oriented API that makes path manipulation readable and chainable (`path.parent.mkdir(parents=True)`), handles platform differences internally, and integrates with `expanduser()`, `resolve()`, and `rglob()` without importing separate functions.

### Why centralized path_utils instead of per-module resolution

A single `resolve_path()` entry point guarantees that every module — current and future — handles `~`, `desktop/`, and protected-path validation identically. Adding a new smart keyword or blocked directory requires changing exactly one file.

### Why stdlib logging over third-party

The stdlib `logging` module supports file handlers, formatters, log levels, and handler composition out of the box. Introducing a third-party logger would add a dependency with no material benefit at this stage. If Phase 5's memory layer requires structured JSON logs, the handler can be swapped without changing any call site.

### Why Intent + Registry instead of direct dispatch

The original dispatcher matched keywords and called handlers directly in a long if-chain. The intent-based architecture separates parsing from execution: `parse_intent()` produces a data object, and `execute_intent()` consumes it. This means an LLM can produce the same `Intent` structure that the text parser produces, and both flow through the same execution path — policy check, registry lookup, handler call. The command registry also enables `get_available_commands()`, which Phase 2's prompt builder will use to tell the LLM what AURA can do.

---

## Phase 2 — What Remains

The following architecture is already in place:

- **Intent system** — `Intent` dataclass, `parse_intent()`, `execute_intent()`
- **Command registry** — `COMMAND_REGISTRY` dict with `get_available_commands()`
- **Policy gate** — `CommandPolicy.validate_intent()` blocks dangerous operations
- **LLM backend abstraction** — `LLMBackend` ABC with `OllamaBackend` stub
- **LLM brain** — `LLMBrain.process()` stub ready for real inference
- **I/O abstraction** — `InputSource` / `OutputSink` contracts

What Phase 2 still needs to build:

- **Whisper STT** — a new `InputSource` implementation that listens to the microphone and yields transcribed text
- **Ollama integration** — replace the `OllamaBackend` stub with real HTTP calls to a local Ollama server
- **Prompt engineering** — build the system prompt from `get_available_commands()` and parse structured LLM output into `Intent` objects
- **Piper TTS** — a new `OutputSink` implementation that speaks `CommandResult.message` aloud
- **Async main loop** — the current blocking `while True` loop needs an async variant for concurrent voice listening and command processing
