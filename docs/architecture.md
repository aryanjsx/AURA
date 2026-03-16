# 🏗️ AURA Architecture — Deep Dive

> How AURA processes a command from input to execution to response.

---

## The 6-Layer Pipeline

AURA is designed as a layered pipeline. Each layer has a single responsibility, communicates only with its immediate neighbours, and can be developed and tested independently.

```
┌──────────────────────────────────────────────────────────┐
│  LAYER 1 — INPUT                                         │
│  Where commands enter the system                         │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │   CLI    │  │  Whisper STT │  │  PyQt6 GUI Input │   │
│  │ (Phase 1)│  │  (Phase 2)   │  │  (Phase 4)       │   │
│  └──────────┘  └──────────────┘  └──────────────────┘   │
├──────────────────────────────────────────────────────────┤
│  LAYER 2 — REASONING                                     │
│  Where commands are understood and routed                │
│  ┌──────────────────┐  ┌─────────────────────────────┐  │
│  │  Dispatcher       │  │  Ollama LLM Intent Parser  │  │
│  │  (regex routing)  │  │  (semantic understanding)   │  │
│  │  (Phase 1)        │  │  (Phase 2)                  │  │
│  └──────────────────┘  └─────────────────────────────┘  │
├──────────────────────────────────────────────────────────┤
│  LAYER 3 — EXECUTION                                     │
│  Where actions happen on the local machine               │
│  ┌──────────────┐ ┌─────────────────┐ ┌──────────────┐  │
│  │ File Manager │ │ Process Manager │ │ System Check │  │
│  └──────────────┘ └─────────────────┘ └──────────────┘  │
│  ┌───────────────────┐ ┌────────────┐                    │
│  │ Project Scaffolder│ │ Log Reader │                    │
│  └───────────────────┘ └────────────┘                    │
├──────────────────────────────────────────────────────────┤
│  LAYER 4 — DEV TOOLS                                     │
│  Domain-specific developer workflow automation           │
│  ┌──────────────┐  ┌──────────────┐                      │
│  │  GitPython   │  │  Docker SDK  │                      │
│  │  (Phase 3)   │  │  (Phase 3)   │                      │
│  └──────────────┘  └──────────────┘                      │
├──────────────────────────────────────────────────────────┤
│  LAYER 5 — OUTPUT                                        │
│  Where results are delivered back to the user            │
│  ┌──────────┐  ┌───────────┐  ┌──────────────────────┐  │
│  │ Console  │  │ Piper TTS │  │  PyQt6 GUI Display   │  │
│  │ (Phase 1)│  │ (Phase 2) │  │  (Phase 4)           │  │
│  └──────────┘  └───────────┘  └──────────────────────┘  │
├──────────────────────────────────────────────────────────┤
│  LAYER 6 — MEMORY                                        │
│  Persistent context and history                          │
│  ┌──────────────┐  ┌──────────────────────────────────┐  │
│  │  File Logs   │  │  ChromaDB Vector Store           │  │
│  │  (Phase 1)   │  │  (Phase 5)                       │  │
│  └──────────────┘  └──────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

---

## How a Command Flows (Phase 1)

```
User types "create file desktop/report.txt"
       │
       ▼
┌─────────────┐
│   aura.py   │  INPUT — reads from stdin
│   (CLI)     │
└──────┬──────┘
       │
       ▼
┌──────────────────┐
│   dispatcher.py  │  REASONING — parses "create file desktop/report.txt"
│                  │  routes to file_manager.create_file("desktop/report.txt")
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│   path_utils.py  │  PATH RESOLUTION — "desktop/report.txt"
│                  │  → ~/Desktop/report.txt → C:\Users\You\Desktop\report.txt
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ file_manager.py  │  EXECUTION — pathlib creates the file at the resolved path
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│   logger.py      │  MEMORY — writes log entry to aura.log
└──────┬───────────┘
       │
       ▼
┌─────────────┐
│   aura.py   │  OUTPUT — prints "File created: C:\Users\You\Desktop\report.txt"
│   (CLI)     │
└─────────────┘
```

---

## How a Command Will Flow (Phase 2+)

```
User says "push the backend to GitHub"
       │
       ▼
┌──────────────┐
│  Whisper STT │  INPUT — transcribes speech to text
└──────┬───────┘
       │
       ▼
┌──────────────────┐
│  Ollama LLM      │  REASONING — understands intent, generates:
│  (Llama 3)       │  git add . && git commit && git push
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│  GitPython       │  DEV TOOLS — executes the git operations
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│  ChromaDB        │  MEMORY — stores action in project context
└──────┬───────────┘
       │
       ▼
┌──────────────┐
│  Piper TTS   │  OUTPUT — speaks "Backend pushed to GitHub"
└──────────────┘
```

---

## Design Principles

1. **Zero cross-dependencies** — modules only depend on shared utilities (`logger`, `path_utils`), never on each other
2. **Centralized path resolution** — every module funnels user paths through `path_utils.resolve_path()`, so `~`, smart keywords, and relative paths are handled uniformly
3. **Pure routing** — the dispatcher maps commands to handlers; adding a new input source (voice, GUI) requires zero changes to execution modules
4. **Offline-first** — no module makes network calls; all tools run locally
5. **Incremental** — each phase adds a new layer without modifying existing ones
6. **Safe by default** — destructive operations are blocked on system-critical directories
7. **Testable** — every function accepts explicit arguments and returns explicit results

---

## Module Map

| Directory | Layer | Phase | Description |
|---|---|---|---|
| `aura.py` | Input + Output | 1 | CLI REPL |
| `command_engine/dispatcher.py` | Reasoning | 1 | Text command router |
| `command_engine/path_utils.py` | Infrastructure | 1 | Centralized path resolution + safety |
| `command_engine/file_manager.py` | Execution | 1 | File CRUD |
| `command_engine/process_manager.py` | Execution | 1 | Shell + process control |
| `command_engine/system_check.py` | Execution | 1 | Tool version probes |
| `command_engine/logger.py` | Memory | 1 | Structured file logging |
| `modules/project_scaffolder.py` | Execution | 1 | Project dir generator |
| `modules/log_reader.py` | Execution | 1 | Log file tail reader |
| `aura-core/` | Input + Reasoning + Output | 2 | Whisper, Ollama, Piper |
| `aura-devtools/` | Dev Tools | 3 | GitPython, Docker SDK |
| `aura-gui/` | Input + Output | 4 | PyQt6 dashboard |
| `aura-memory/` | Memory | 5 | ChromaDB vector store |
