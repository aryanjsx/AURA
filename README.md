# ⚡ AURA — Autonomous Utility & Resource Assistant

<p align="center">
  <img src="docs/assets/AURA.jpg" alt="AURA — Autonomous Utility & Resource Assistant" width="800"/>
</p>

![Build Status](https://github.com/aryanjsx/AURA/actions/workflows/ci.yml/badge.svg)
![License](https://img.shields.io/github/license/aryanjsx/AURA)
![Stars](https://img.shields.io/github/stars/aryanjsx/AURA?style=social)
![Issues](https://img.shields.io/github/issues/aryanjsx/AURA)
![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)
![Status](https://img.shields.io/badge/status-in%20development-yellow)

> A fully offline AI developer assistant that automates coding workflows using local LLMs, voice commands, and system automation — no cloud, no API keys, no subscriptions.

🔒 Fully Offline · No Cloud · No API Keys · Local LLMs · Voice-Controlled · Developer-First

<!--
![AURA Demo](docs/assets/demo.gif)
-->

---

## 🚧 Current Status

AURA is in active development. The repository is public from Day 1 so contributors can follow the build, propose ideas, and prepare to contribute as each phase completes.

| Phase | Description | Status | ETA |
|-------|-------------|--------|-----|
| Phase 1 — Python Automation Core | Command engine, file ops, process control | ✅ Complete | — |
| Phase 2 — Voice Pipeline | Whisper STT + Ollama LLM + Piper TTS | ⏳ Planned | Week 9 |
| Phase 3 — Dev Tools | Git & Docker automation | ⏳ Planned | Week 13 |
| Phase 4 — GUI Dashboard | PyQt6 desktop interface | ⏳ Planned | Week 16 |
| Phase 5 — Memory Layer | ChromaDB semantic memory | ⏳ Planned | Week 18 |

---

## ✨ Features

### Phase 1 — Available Now

- **Command Execution Engine** — dispatch natural-language text commands to file, process, and system handlers
- **Structured Results** — every handler returns a `CommandResult` with `success`, `message`, and typed `data` payload, ready for programmatic consumers (LLM, GUI)
- **Smart Path Resolution** — `~`, `desktop/`, `downloads/`, `documents/` keywords are automatically expanded to real absolute paths across all modules
- **File Operations** — create, delete, rename, move, and glob-search files anywhere on your machine
- **Path Safety** — protected system directories (`C:\Windows`, `/usr`, etc.) are blocked using full ancestry checking, with path-traversal protection on renames
- **Shell Safety** — dangerous commands (`rm -rf /`, `format c:`, `dd`, etc.) are blocked before they reach `subprocess`
- **Process Management** — run shell commands, inspect running processes, kill by name
- **System Health Checks** — instantly verify Python, Git, Node, and Docker availability (configurable tool list)
- **Project Scaffolding** — spin up a new project skeleton anywhere (`create project ~/Desktop/my_app`) with configurable folder layout
- **Log Inspection** — tail any log file without leaving the assistant
- **Config-Driven** — all settings (protected paths, log levels, tool lists, timeouts) loaded from `config.yaml` with safe fallback defaults
- **Structured Logging** — every action, result, and error timestamped to `logs/aura.log` with automatic log rotation
- **I/O Abstraction** — pluggable `InputSource` / `OutputSink` interfaces so Phase 2 can swap in voice input and TTS output with zero changes to the engine
- **Intent System** — structured `Intent` dataclass decouples text parsing from command execution, enabling LLM-generated actions in Phase 2
- **Command Registry** — programmatic registry of all commands with metadata, powering LLM tool-use discovery and dynamic help
- **Command Policy** — centralized `CommandPolicy` safety gate validates every intent before any handler runs
- **LLM Backend Abstraction** — pluggable `LLMBackend` interface with Ollama stub, ready for real model integration

### Coming Soon

- **Voice Control** — speak commands, hear responses (Whisper + Piper)
- **Local LLM Reasoning** — intent parsing and code generation via Ollama (Llama 3)
- **Git Automation** — commit, push, branch, and auto-generate commit messages
- **Docker Management** — build, run, stop containers from a single command
- **Desktop GUI** — PyQt6 dashboard with live command log
- **Persistent Memory** — ChromaDB-powered semantic project context

---

## 🏗️ Architecture

AURA is built as a 6-layer pipeline where each layer is a standalone module with zero cross-dependencies:

```
┌─────────────────────────────────────────────────────┐
│                     INPUT LAYER                     │
│           CLI (Phase 1) · Voice (Phase 2)           │
├─────────────────────────────────────────────────────┤
│                  REASONING LAYER                    │
│        Command Dispatcher · Ollama LLM (Phase 2)    │
├─────────────────────────────────────────────────────┤
│                  EXECUTION LAYER                    │
│     File Manager · Process Manager · System Check   │
├─────────────────────────────────────────────────────┤
│                  DEV TOOLS LAYER                    │
│        GitPython (Phase 3) · Docker SDK (Phase 3)   │
├─────────────────────────────────────────────────────┤
│                   OUTPUT LAYER                      │
│        Console · Piper TTS (Phase 2) · GUI (Phase 4)│
├─────────────────────────────────────────────────────┤
│                  MEMORY LAYER                       │
│            ChromaDB (Phase 5) · Logs                │
└─────────────────────────────────────────────────────┘
```

### Project Structure

```
AURA/
├── aura.py                        # CLI entry-point (uses I/O abstraction)
├── config.example.yaml            # Configuration template (copy to config.yaml)
│
├── core/                          # System layer — types, config, abstractions
│   ├── intent.py                  # Intent dataclass (text/LLM → structured action)
│   ├── policy.py                  # CommandPolicy safety gate
│   ├── context.py                 # AppContext (config + policy + session state)
│   ├── config_loader.py           # YAML config with fallback defaults
│   ├── io.py                      # InputSource / OutputSink abstractions
│   ├── result.py                  # CommandResult structured return type
│   └── backends/                  # LLM provider abstraction
│       ├── base.py                # LLMBackend ABC
│       ├── ollama_backend.py      # Ollama stub (Phase 2)
│       └── factory.py             # Backend factory
│
├── command_engine/                # Automation backbone
│   ├── dispatcher.py              # Intent-based command router + registry
│   ├── path_utils.py              # Centralized path resolution + safety
│   ├── file_manager.py            # File CRUD (pathlib + shutil)
│   ├── process_manager.py         # subprocess + psutil wrappers + shell safety
│   ├── system_check.py            # Developer tool version probes
│   └── logger.py                  # Config-driven rotating file + console logger
│
├── modules/                       # Higher-level utilities
│   ├── project_scaffolder.py      # Config-driven project directory generator
│   └── log_reader.py              # Efficient log file tail reader
│
├── tests/                         # Unit tests (pytest)
│   ├── test_file_manager.py
│   ├── test_process_manager.py
│   └── test_system_check.py
│
├── logs/                          # Runtime log output (auto-created, rotated)
├── docs/                          # Architecture and design documents
│
├── aura-core/                     # [Future] Whisper STT + Piper TTS voice I/O
├── aura-devtools/                 # [Future] Git & Docker automation
├── aura-gui/                      # [Future] PyQt6 dashboard
└── aura-memory/                   # [Future] ChromaDB memory layer
```

> Active development happens in `core/`, `command_engine/`, and `modules/`. Folders prefixed with `aura-` are expansion placeholders for future phases and do not contain implementation code yet.

---

## 🛠️ Tech Stack

| Layer | Technology | Status |
|---|---|---|
| Language | Python 3.10+ | ✅ Active |
| Configuration | PyYAML (`config.yaml` with fallback defaults) | ✅ Active |
| Path Resolution | `pathlib` (centralized via `path_utils`) | ✅ Active |
| File I/O | `pathlib`, `shutil` | ✅ Active |
| Process Control | `subprocess`, `psutil` | ✅ Active |
| Logging | `logging` (stdlib, `RotatingFileHandler`) | ✅ Active |
| Speech-to-Text | Whisper | ⏳ Phase 2 |
| Local LLM | Ollama (Llama 3) | ⏳ Phase 2 |
| Text-to-Speech | Piper TTS | ⏳ Phase 2 |
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

Edit `config.yaml` to customize protected paths, logging levels, shell timeouts, system-check tools, and project scaffolding folders. If you skip this step, AURA uses sensible defaults from `config.example.yaml`.

### Run

```bash
python aura.py
```

```
    ___   __  ______  ___
   /   | / / / / __ \/   |
  / /| |/ / / / /_/ / /| |
 / ___ / /_/ / _, _/ ___ |
/_/  |_\____/_/ |_/_/  |_|

Autonomous Utility & Resource Assistant
Phase 1 — Command Execution Engine

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
(full command reference)

> exit
Goodbye.
```

### Available Commands

| Command | Description |
|---|---|
| `create file <path>` | Create an empty file |
| `delete file <path>` | Delete a file |
| `rename file <old> <new>` | Rename a file |
| `move file <src> <dst>` | Move a file |
| `search files <dir> <pattern>` | Glob-search for files |
| `run command <cmd>` | Execute a shell command |
| `list processes` | Show top processes by memory |
| `kill process <name>` | Terminate processes by name |
| `check system health` | Check Python, Git, Node, Docker |
| `create project <name\|path>` | Scaffold a new project |
| `show logs <file> [n]` | Tail a log file (default 20 lines) |
| `help` | Show in-app help |
| `exit` / `quit` | Exit the CLI |

> All paths support `~` (home directory), smart keywords (`desktop/`, `downloads/`, `documents/`), and absolute paths. Files are always created at the correct location, not inside the AURA project folder.

> Full voice and LLM-driven interaction coming in Phase 2+.

---

## 📋 Roadmap

See [ROADMAP.md](ROADMAP.md) for the detailed phase breakdown.

| Phase | What Ships | Key Tech |
|---|---|---|
| **1** ✅ | Command Execution Engine + CLI | Python, subprocess, psutil, PyYAML |
| **2** ⏳ | Offline Voice Pipeline — hear, think, speak | Whisper, Ollama, Piper |
| **3** ⏳ | Developer Tools — Git & Docker automation | GitPython, Docker SDK |
| **4** ⏳ | Desktop GUI — visual dashboard | PyQt6 |
| **5** ⏳ | Memory Layer — semantic project context | ChromaDB |

---

## 🙋 Where We Need Help

### Currently Open (Phase 1)
- Additional test coverage (dispatcher, path_utils, scaffolder, log_reader)
- Custom `InputSource` / `OutputSink` implementations for new frontends
- Documentation improvements
- Config schema validation and documentation

### Opening Soon (Phase 2)
- Whisper STT integration and optimization
- Ollama prompt engineering for developer tasks
- Piper TTS voice configuration
- Command registry for LLM tool-use discovery

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
