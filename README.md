# ⚡ AURA — Autonomous Utility & Resource Assistant

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
- **File Operations** — create, delete, rename, move, and glob-search files from a single prompt
- **Process Management** — run shell commands, inspect running processes, kill by name
- **System Health Checks** — instantly verify Python, Git, Node, and Docker availability
- **Project Scaffolding** — spin up a new project skeleton (`backend/`, `frontend/`, `.gitignore`) in one command
- **Log Inspection** — tail any log file without leaving the assistant
- **Structured Logging** — every action, result, and error timestamped to `logs/aura.log`

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
│                     INPUT LAYER                      │
│           CLI (Phase 1) · Voice (Phase 2)            │
├─────────────────────────────────────────────────────┤
│                  REASONING LAYER                     │
│        Command Dispatcher · Ollama LLM (Phase 2)     │
├─────────────────────────────────────────────────────┤
│                  EXECUTION LAYER                     │
│     File Manager · Process Manager · System Check    │
├─────────────────────────────────────────────────────┤
│                  DEV TOOLS LAYER                     │
│        GitPython (Phase 3) · Docker SDK (Phase 3)    │
├─────────────────────────────────────────────────────┤
│                   OUTPUT LAYER                       │
│         Console · Piper TTS (Phase 2) · GUI (Phase 4)│
├─────────────────────────────────────────────────────┤
│                   MEMORY LAYER                       │
│             ChromaDB (Phase 5) · Logs                │
└─────────────────────────────────────────────────────┘
```

### Project Structure

```
AURA/
├── README.md
├── LICENSE
├── CONTRIBUTING.md
├── CODE_OF_CONDUCT.md
├── ROADMAP.md
├── CHANGELOG.md
├── SECURITY.md
├── .gitignore
│
├── .github/
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug_report.md
│   │   ├── feature_request.md
│   │   └── module_proposal.md
│   ├── PULL_REQUEST_TEMPLATE.md
│   └── workflows/
│       └── ci.yml
│
├── docs/
│   └── architecture.md
│
├── aura.py                        # CLI entry-point
├── command_engine/                 # Core automation backbone
│   ├── dispatcher.py              # Text command → handler router
│   ├── file_manager.py            # File CRUD (pathlib + shutil)
│   ├── process_manager.py         # subprocess + psutil wrappers
│   ├── system_check.py            # Developer tool version probes
│   └── logger.py                  # Centralized file + console logger
│
├── modules/                       # Higher-level utilities
│   ├── project_scaffolder.py      # Project directory generator
│   └── log_reader.py              # Efficient log file tail reader
│
├── logs/                          # Runtime log output (auto-created)
│
├── aura-core/                     # [Planned] STT, LLM, TTS pipeline
├── aura-devtools/                 # [Planned] Git & Docker automation
├── aura-gui/                      # [Planned] PyQt6 dashboard
└── aura-memory/                   # [Planned] ChromaDB memory layer
```

> Each module folder is clearly scoped so contributors immediately know where their code belongs.

---

## 🛠️ Tech Stack

| Layer | Technology | Status |
|---|---|---|
| Language | Python 3.10+ | ✅ Active |
| File I/O | `pathlib`, `shutil` | ✅ Active |
| Process Control | `subprocess`, `psutil` | ✅ Active |
| Logging | `logging` (stdlib) | ✅ Active |
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

> create file hello.txt
File created: hello.txt

> check system health
System Health:
  python     : Python 3.14.0
  git        : git version 2.51.1
  node       : v24.11.0
  docker     : NOT INSTALLED

> create project my-app
Project 'my-app' created at C:\...\my-app

> run command echo Hello World
Hello World
(exit code 0)

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
| `create project <name>` | Scaffold a new project |
| `show logs <file> [n]` | Tail a log file (default 20 lines) |
| `help` | Show in-app help |
| `exit` / `quit` | Exit the CLI |

> Full voice and LLM-driven interaction coming in Phase 2+.

---

## 📋 Roadmap

See [ROADMAP.md](ROADMAP.md) for the detailed phase breakdown.

| Phase | What Ships | Key Tech |
|---|---|---|
| **1** ✅ | Command Execution Engine + CLI | Python, subprocess, psutil |
| **2** ⏳ | Offline Voice Pipeline — hear, think, speak | Whisper, Ollama, Piper |
| **3** ⏳ | Developer Tools — Git & Docker automation | GitPython, Docker SDK |
| **4** ⏳ | Desktop GUI — visual dashboard | PyQt6 |
| **5** ⏳ | Memory Layer — semantic project context | ChromaDB |

---

## 🙋 Where We Need Help

### Currently Open (Phase 1)
- Python automation module testing
- Documentation improvements
- `.gitignore` and project config refinements

### Opening Soon (Phase 2)
- Whisper STT integration and optimization
- Ollama prompt engineering for developer tasks
- Piper TTS voice configuration

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
3. Commit using [Conventional Commits](https://www.conventionalcommits.org/) (`feat(aura-core): add amazing feature`)
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
