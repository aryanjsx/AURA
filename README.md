# ⚡ AURA — Autonomous Utility & Resource Assistant

![License](https://img.shields.io/github/license/aryanjsx/AURA)
![Stars](https://img.shields.io/github/stars/aryanjsx/AURA?style=social)
![Issues](https://img.shields.io/github/issues/aryanjsx/AURA)
![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)
![Status](https://img.shields.io/badge/status-in%20development-yellow)

> A fully offline, local-first AI developer assistant that automates your entire workflow — no cloud, no API keys, no compromises.

<!--
TODO: Add demo GIF or architecture diagram here
![AURA Demo](docs/assets/demo.gif)
-->

---

## ✨ Features

- **Command Execution Engine** — dispatch natural-language commands to file, process, and system handlers
- **File Operations** — create, delete, rename, move, and glob-search files from a single prompt
- **Process Management** — run shell commands, inspect running processes, kill by name
- **System Health Checks** — instantly verify Python, Git, Node, and Docker availability
- **Project Scaffolding** — spin up a new project skeleton (`backend/`, `frontend/`, `.gitignore`) in one command
- **Log Inspection** — tail any log file without leaving the assistant
- **Structured Logging** — every action, result, and error timestamped to `logs/aura.log`
- **100% Offline** — zero network calls, zero telemetry, runs entirely on your machine

---

## 🏗️ Architecture

```
aura/
├── aura.py                        # CLI entry-point (REPL loop)
│
├── command_engine/                 # Core automation backbone
│   ├── dispatcher.py              # Text command → handler router
│   ├── file_manager.py            # File CRUD via pathlib / shutil
│   ├── process_manager.py         # subprocess + psutil wrappers
│   ├── system_check.py            # Developer-tool version probes
│   └── logger.py                  # Centralized rotating logger
│
├── modules/                       # Higher-level utilities
│   ├── project_scaffolder.py      # Directory-tree generator
│   └── log_reader.py              # Efficient file-tail reader
│
├── logs/                          # Runtime log output (auto-created)
├── requirements.txt
└── README.md
```

**Design principles:** each module is self-contained with no cross-dependencies (only the logger is shared). The dispatcher is a pure router — adding future input sources (voice, LLM, GUI) requires zero changes to the engine modules.

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.10+ |
| File I/O | `pathlib`, `shutil` |
| Process control | `subprocess`, `psutil` |
| Logging | `logging` (stdlib) |
| External deps | **psutil** (sole runtime dependency) |

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

> help
(full command reference)

> exit
Goodbye.
```

> Full voice and LLM-driven interaction coming in Phase 2+.

---

## 📋 Roadmap

| Phase | Module | Status |
|---|---|---|
| **1** | Command Execution Engine + CLI | ✅ Complete |
| **2** | Whisper — Speech-to-Text input | 🔲 Planned |
| **3** | Ollama — Local LLM reasoning | 🔲 Planned |
| **4** | Piper — Text-to-Speech output | 🔲 Planned |
| **5** | GitPython — Version control automation | 🔲 Planned |
| **6** | Docker SDK — Container management | 🔲 Planned |
| **7** | PyQt6 — Graphical interface | 🔲 Planned |
| **8** | ChromaDB — Persistent memory layer | 🔲 Planned |

<!-- See [ROADMAP.md](ROADMAP.md) for the full breakdown. -->

---

## 🤝 Contributing

Contributions, issues, and feature requests are welcome!

<!-- See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines. -->

1. Fork the repo
2. Create your branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m "Add amazing feature"`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
