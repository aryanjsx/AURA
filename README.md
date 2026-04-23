# ⚡ AURA — Autonomous Utility & Resource Assistant

<p align="center">
  <img src="docs/assets/AURA.jpg" alt="AURA — Autonomous Utility & Resource Assistant" width="800"/>
</p>

![Build Status](https://github.com/aryanjsx/AURA/actions/workflows/ci.yml/badge.svg)
![License](https://img.shields.io/github/license/aryanjsx/AURA)
![Stars](https://img.shields.io/github/stars/aryanjsx/AURA?style=social)
![Issues](https://img.shields.io/github/issues/aryanjsx/AURA)
![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)
![Status](https://img.shields.io/badge/phase_0-completed-brightgreen)
![Status](https://img.shields.io/badge/phase_1-completed-brightgreen)
![Status](https://img.shields.io/badge/phase_2-in_progress-yellow)

> A fully offline AI developer assistant that automates coding workflows using local LLMs, voice commands, and system automation — no cloud, no API keys, no subscriptions.

🔒 Fully Offline · No Cloud · No API Keys · Local LLMs · Voice-Controlled · Developer-First

<!--
![AURA Demo](docs/assets/demo.gif)
-->

---

## 🚀 Project Status

- **Phase 0:** ✅ Completed
- **Phase 1:** ✅ Completed
- **Phase 2:** 🔄 In Progress

- **Phase 0** → Core system (event bus, config, registry, CLI)
- **Phase 1** → Secure execution layer (sandbox, permissions, audit, non-bypassable architecture)
- **Phase 2** → Intelligence layer (LLM, voice, tool orchestration)

The Phase-0 execution backbone (secure dispatch, argv-based subprocess with `shell=False`, command policy, path safety, npm executor, structured `CommandResult`) is built, and Phase 1 closed it with the non-bypassable `CommandRegistry` pipeline, tamper-evident audit chain, plugin manifest binding, rate limiting, and sandboxed worker isolation. The system is **production-ready for the Phase 0 + Phase 1 scope**; Phase 2 (voice, local LLM, orchestration) is now the active work.

| Phase | Description | Status | ETA |
|-------|-------------|--------|-----|
| Phase 0 — Core Infrastructure | Event bus, config loader, registry, CLI, execution backbone | ✅ Completed | — |
| Phase 1 — Python Automation Core + Secure Execution | File / process / npm / monitor plugins, sandbox, permissions, audit chain, non-bypassable registry | ✅ Completed | — |
| Phase 2 — Intelligence Layer (Voice + LLM) | Whisper STT + Ollama LLM + Piper TTS + tool orchestration | 🔄 In Progress | Week 9 |
| Phase 3 — Dev Tools | Git & Docker automation | ⏳ Planned | Week 13 |
| Phase 4 — GUI Dashboard | PyQt6 desktop interface | ⏳ Planned | Week 16 |
| Phase 5 — Memory Layer | ChromaDB semantic memory | ⏳ Planned | Week 18 |

---

## ✨ Features

### Phase 0 + Phase 1 — Available Now (Completed)

- **Command Execution Engine** — dispatch natural-language text commands to file, process, npm, system, and monitor handlers
- **Structured Results** — every handler returns a `CommandResult` with `success`, `message`, and typed `data` payload, ready for programmatic consumers (LLM, GUI)
- **Smart Path Resolution** — `~`, `desktop/`, `downloads/`, `documents/` keywords are automatically expanded to real absolute paths across all modules
- **File Operations** — create, delete, rename, move, and glob-search files anywhere on your machine
- **Path Safety** — protected system directories (`C:\Windows`, `/usr`, etc.) are blocked using full ancestry checking, with path-traversal protection on renames; optional **`AURA_PROTECTED_PATHS`** env override
- **Shell Safety** — user commands are split into argv and run with **`subprocess`…`shell=False`**; **`CommandPolicy`** applies a **denylist** (destructive patterns) and an **allowlist** of executable names before any generic `run command` reaches the process layer
- **npm** — dedicated executor resolves **`npm`** or **`npm.cmd`** via **`shutil.which`**, validates project directory through **`path_utils`**, runs **`npm install`** / **`npm run <script>`** as argv lists (never a shell string)
- **System Monitoring** — short phrases (`cpu`, `ram`, `memory usage`, `processes`, `show processes`, and more) map to CPU/RAM snapshots and process lists via **psutil**
- **Process Management** — run allowed shell commands, inspect running processes, kill by name
- **System Health Checks** — verify Python, Git, Node, and Docker availability (configurable tool list) using argv-based probes
- **Project Scaffolding** — spin up a new project skeleton anywhere (`create project ~/Desktop/my_app`) with configurable folders and files from config
- **Log Inspection** — tail any log file without leaving the assistant
- **Built-in Help** — `help` / `--help` via the dispatcher returns a Phase-0 command summary; interactive REPL also has a static help banner
- **Config-Driven** — settings (protected paths, log levels, tool lists, timeouts) from `config.yaml` with safe defaults; optional env overrides: **`AURA_LOG_PATH`**, **`AURA_SHELL_TIMEOUT`**, **`AURA_PROTECTED_PATHS`**
- **Structured Logging** — every action, result, and error timestamped to `logs/aura.log` with automatic log rotation
- **I/O Abstraction** — pluggable `InputSource` / `OutputSink` interfaces so the Phase 2 voice input and TTS output plug in with zero changes to the engine
- **Intent System** — structured `Intent` dataclass decouples text parsing from command execution, enabling LLM-generated actions in Phase 2 (in progress)
- **Command Registry** — programmatic registry of all commands with metadata, powering LLM tool-use discovery and dynamic help
- **Command Policy** — centralized `CommandPolicy` safety gate validates every intent before any handler runs
- **LLM Backend Abstraction** — pluggable `LLMBackend` interface with Ollama stub, ready for real model integration

### Phase 2 — In Progress (Intelligence Layer)

- **Voice Control** — speak commands, hear responses (Whisper + Piper)
- **Local LLM Reasoning** — intent parsing and code generation via Ollama (Llama 3)
- **Tool Orchestration** — LLM-driven multi-step plans routed through the existing registry + safety pipeline

### Coming After Phase 2

- **Git Automation** — commit, push, branch, and auto-generate commit messages (Phase 3)
- **Docker Management** — build, run, stop containers from a single command (Phase 3)
- **Desktop GUI** — PyQt6 dashboard with live command log (Phase 4)
- **Persistent Memory** — ChromaDB-powered semantic project context (Phase 5)

---

## 🏗️ Architecture

AURA is built as a layered pipeline where each layer is a standalone module with clear boundaries. Full detail lives in **[docs/architecture.md](docs/architecture.md)**.

```
┌─────────────────────────────────────────────────────┐
│                     INPUT LAYER                     │
│  CLI · one-shot `python -m aura "…"` · Voice (Phase 2 – in progress) │
├─────────────────────────────────────────────────────┤
│                  REASONING LAYER                    │
│   Command Dispatcher · Ollama LLM (Phase 2 – in progress) │
├─────────────────────────────────────────────────────┤
│                  EXECUTION LAYER                    │
│  File Manager · Process Manager · npm · System Check │
├─────────────────────────────────────────────────────┤
│                  DEV TOOLS LAYER                    │
│        GitPython (Phase 3) · Docker SDK (Phase 3)   │
├─────────────────────────────────────────────────────┤
│                   OUTPUT LAYER                      │
│  Console · Piper TTS (Phase 2 – in progress) · GUI (Phase 4) │
├─────────────────────────────────────────────────────┤
│                  MEMORY LAYER                       │
│            ChromaDB (Phase 5) · Logs                │
└─────────────────────────────────────────────────────┘
```

### Project Structure

```
AURA/
├── plugins_manifest.yaml          # Authoritative plugin safety manifest
├── config.example.yaml            # Configuration template (copy to config.yaml)
│
├── aura/                          # Main-process package — core, runtime, IPC client
│   ├── __main__.py                # ``python -m aura`` entry point
│   ├── cli.py                     # CLI bootstrap + REPL / one-shot
│   ├── core/                      # Infrastructure + security primitives
│   │   ├── command_registry.py    # Sole authorized execution entry point
│   │   ├── router.py              # Text → Intent → registry pipeline
│   │   ├── execution_engine.py    # In-process dispatch (sealed, private)
│   │   ├── worker_client.py       # IPC proxy to the isolated worker (sealed)
│   │   ├── planner.py             # Multi-step TaskPlan execution + rollback
│   │   ├── plugin_loader.py       # Plugin discovery and registration
│   │   ├── plugin_manifest.py     # Cross-process manifest + SHA-256 binding
│   │   ├── plugin_base.py         # Plugin / IntentParser contracts
│   │   ├── safety_gate.py         # Non-blocking confirmation prompt
│   │   ├── sandbox.py             # Filesystem sandbox + symlink escape block
│   │   ├── policy.py              # Shell argv allowlist / denylist
│   │   ├── permissions.py         # PermissionLevel validator
│   │   ├── rate_limiter.py        # Per-source sliding-window limiter
│   │   ├── audit_log.py           # Tamper-evident hash-chained audit log
│   │   ├── audit_events.py        # Dynamic audit event registry
│   │   ├── event_bus.py           # Pub/sub event bus
│   │   ├── logger.py              # Structured JSON logger
│   │   ├── config_loader.py       # YAML + env override loader (strict validation)
│   │   ├── error_handler.py       # Centralized error-to-message translator
│   │   ├── errors.py              # Typed error hierarchy (AuraError, …)
│   │   ├── intent.py              # Intent dataclass (no caller-trusted source)
│   │   ├── schema.py              # CommandSpec + action-name validation
│   │   ├── param_schema.py        # Per-command parameter schema + size caps
│   │   ├── tracing.py             # Trace-ID context var
│   │   ├── result.py              # CommandResult return type
│   │   └── io.py                  # Input / output abstractions
│   │
│   ├── worker/                    # Isolated execution subprocess
│   │   ├── server.py              # JSON-line IPC server + manifest hash verify
│   │   ├── __main__.py            # ``python -m aura.worker`` entry point
│   │   └── __init__.py
│   │
│   └── intents/                   # Main-process text → Intent parsers
│       └── system_intents.py
│
├── plugins/                       # Worker-only plugin code (import-guarded)
│   └── system/                    # Built-in system plugin
│       ├── plugin.py              # Plugin registration surface
│       └── executor.py            # File / process / npm / monitor executors
│
├── tests/                         # pytest suite (214 tests incl. lockdown probes)
├── docs/                          # Architecture, phase plans, design docs
│   ├── architecture.md
│   └── phases.md                  # Layout for Phase 2 (in progress) + Phase 3–5 plans
├── public/                        # GitHub Pages site (deployed via pages.yml)
└── logs/                          # Runtime log output (auto-created, rotated)
```

> Active code lives under `aura/` and `plugins/`.  Future phases (voice, devtools, GUI, memory) will land inside the same `aura/` / `plugins/` tree — see [`docs/phases.md`](docs/phases.md) for the planned layout of each.

---

## 🛠️ Tech Stack

| Layer | Technology | Status |
|---|---|---|
| Language | Python 3.10+ | ✅ Active |
| Configuration | PyYAML (`config.yaml` with fallback defaults + env overrides) | ✅ Active |
| Path Resolution | `pathlib` (centralized via `path_utils`) | ✅ Active |
| File I/O | `pathlib`, `shutil` | ✅ Active |
| Process Control | `subprocess` (argv, `shell=False`), `psutil` | ✅ Active |
| Logging | `logging` (stdlib, `RotatingFileHandler`) | ✅ Active |
| Speech-to-Text | Whisper | 🔄 Phase 2 (in progress) |
| Local LLM | Ollama (Llama 3) | 🔄 Phase 2 (in progress) |
| Text-to-Speech | Piper TTS | 🔄 Phase 2 (in progress) |
| Version Control | GitPython | ⏳ Phase 3 |
| Containers | Docker SDK | ⏳ Phase 3 |
| GUI Framework | PyQt6 | ⏳ Phase 4 |
| Vector Memory | ChromaDB | ⏳ Phase 5 |

---

## 🚀 Getting Started

### Prerequisites

- Python 3.10 or newer

### Install

```bash
git clone https://github.com/aryanjsx/AURA.git
cd AURA
pip install -r requirements.txt
```

### Configure (optional)

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml` to customize protected paths, logging levels, shell timeouts, system-check tools, and project scaffolding. If you skip this step, AURA uses sensible defaults from `config.example.yaml`.

Optional environment overrides (see `config_loader` docstring): `AURA_LOG_PATH`, `AURA_SHELL_TIMEOUT`, `AURA_PROTECTED_PATHS`.

### Run

**Interactive REPL**

```bash
python -m aura
```

**One-shot command** (runs a single dispatch and exits)

```bash
python -m aura "cpu"
python -m aura "npm install"
```

```
    ___   __  ______  ___
   /   | / / / / __ \/   |
  / /| |/ / / / /_/ / /| |
 / ___ / /_/ / _, _/ ___ |
/_/  |_\____/_/ |_/_/  |_|

Autonomous Utility & Resource Assistant
Phase 0 + Phase 1 — Secure Command Execution Engine (Completed)

> create file ~/Desktop/hello.txt
File created: C:\Users\You\Desktop\hello.txt

> create file desktop/notes.txt
File created: C:\Users\You\Desktop\notes.txt

> move file ~/Desktop/notes.txt ~/Documents/
Moved: C:\Users\You\Desktop\notes.txt -> C:\Users\You\Documents\notes.txt

> check system health
System Health:
  python     : Python 3.14.0
  git        : git version 2.51.1
  node       : v24.11.0
  docker     : NOT INSTALLED

> create project ~/Desktop/my-app
Project 'my-app' created at C:\Users\You\Desktop\my-app

> help
(full command reference from aura.cli._build_help)

> exit
Goodbye.
```

### Available Commands

| Command | Description |
|---|---|
| **Monitoring** | `cpu`, `cpu usage`, `get cpu usage`, `ram`, `memory`, `memory usage`, `processes`, `show processes`, `running processes` |
| **npm** | `npm install [path]`, `npm run <script> [path]` |
| `create file <path>` | Create an empty file |
| `delete file <path>` | Delete a file |
| `rename file <old> <new>` | Rename a file |
| `move file <src> <dst>` | Move a file |
| `search files <dir> <pattern>` | Glob-search for files |
| `run command <cmd>` | Execute an allowed command (argv; see policy allowlist) |
| `list processes` | Show top processes by memory (same handler as short `processes` phrases) |
| `kill process <name>` | Terminate processes by name |
| `check system health` | Check Python, Git, Node, Docker |
| `create project <name\|path>` | Scaffold a new project |
| `show logs <file> [n]` | Tail a log file (default 20 lines) |
| `help` / `--help` | Phase-0 help via dispatcher (one-shot); interactive `help` shows REPL banner help |
| `exit` / `quit` | Exit the CLI |

> All paths support `~` (home directory), smart keywords (`desktop/`, `downloads/`, `documents/`), and absolute paths. Files are always created at the correct location, not inside the AURA project folder.

> Full voice and LLM-driven interaction arrives with Phase 2 (in progress).

---

## 📋 Roadmap

See [ROADMAP.md](ROADMAP.md) for the detailed phase breakdown.

| Phase | What Ships | Key Tech |
|---|---|---|
| **0** ✅ | Core Infrastructure — event bus, config, registry, CLI, execution backbone | Python, PyYAML |
| **1** ✅ | Python Automation Core + Secure Execution — file/process/npm/monitor plugins, sandbox, permissions, audit chain, non-bypassable registry | subprocess (argv), psutil, hashlib, hmac |
| **2** 🔄 | Intelligence Layer — offline voice + LLM + tool orchestration | Whisper, Ollama, Piper |
| **3** ⏳ | Developer Tools — Git & Docker automation | GitPython, Docker SDK |
| **4** ⏳ | Desktop GUI — visual dashboard | PyQt6 |
| **5** ⏳ | Memory Layer — semantic project context | ChromaDB |

---

## 🙋 Where We Need Help

### Phase 0 + Phase 1 — Completed (maintenance / hardening)
- Additional test coverage (npm executor, scaffolder edge cases)
- Custom `InputSource` / `OutputSink` implementations for new frontends
- Documentation improvements
- Config schema validation and documentation

### Phase 2 — In Progress (active contributions welcome)
- Whisper STT integration and optimization
- Ollama prompt engineering for developer tasks
- Piper TTS voice configuration
- LLM tool-use orchestration on top of the existing command registry

### Future (Phase 3+)
- Git automation edge cases
- Docker SDK integration
- PyQt6 dashboard components
- ChromaDB memory schema design

---

## 🤝 Contributing

Contributions, issues, and feature requests are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for full guidelines.

**Quick start:**

1. Fork the repo
2. Create your branch (`git checkout -b feat/amazing-feature`)
3. Commit using [Conventional Commits](https://www.conventionalcommits.org/) (`feat(core): add amazing feature`)
4. Push to your branch (`git push origin feat/amazing-feature`)
5. Open a Pull Request

See the [issues tab](https://github.com/aryanjsx/AURA/issues) — look for `good first issue` and `help wanted` labels.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).

---

<p align="center">
  <b>⚡ AURA — Built offline. Powered locally. Yours completely.</b><br>
  No cloud · No API keys · No internet · Full data privacy<br><br>
  <a href="https://github.com/aryanjsx">aryanjsx</a>
</p>
