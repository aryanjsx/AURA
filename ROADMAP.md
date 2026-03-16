# 📋 AURA Roadmap

> A fully offline AI developer assistant — from command-line automation to voice-controlled coding workflows.

---

## Phase 1 — Python Automation Core ✅

**Status:** Complete

The foundation. A modular command-execution engine accessible through a CLI.

| Deliverable | Module | Status |
|---|---|---|
| Command dispatcher (text → action router) | `command_engine/dispatcher.py` | ✅ Done |
| Centralized path resolution (`~`, smart keywords, safety) | `command_engine/path_utils.py` | ✅ Done |
| File operations (create, delete, rename, move, search) | `command_engine/file_manager.py` | ✅ Done |
| Process management (run, list, kill) | `command_engine/process_manager.py` | ✅ Done |
| System health checker (Python, Git, Node, Docker) | `command_engine/system_check.py` | ✅ Done |
| Centralized structured logging | `command_engine/logger.py` | ✅ Done |
| Project scaffolder (supports full paths) | `modules/project_scaffolder.py` | ✅ Done |
| Log file reader (supports full paths) | `modules/log_reader.py` | ✅ Done |
| Interactive CLI interface | `aura.py` | ✅ Done |

---

## Phase 2 — Offline Voice Pipeline ⏳

**Status:** Planned · **ETA:** Week 9

The transformation. AURA hears you, thinks locally, and speaks back.

| Deliverable | Tech | Module |
|---|---|---|
| Microphone listener + speech-to-text | Whisper (OpenAI) | `aura-core/` |
| Intent parsing + command generation | Ollama (Llama 3) | `aura-core/` |
| Voice response synthesis | Piper TTS | `aura-core/` |
| Prompt engineering for dev-task classification | — | `aura-core/` |
| End-to-end voice → action → response pipeline | — | `aura-core/` |

---

## Phase 3 — Developer Tools ⏳

**Status:** Planned · **ETA:** Week 13

Real developer workflow automation — Git and Docker from voice or text.

| Deliverable | Tech | Module |
|---|---|---|
| Git automation (commit, push, branch, status) | GitPython | `aura-devtools/` |
| AI-generated commit messages | Ollama | `aura-devtools/` |
| Docker container lifecycle (build, run, stop, logs) | Docker SDK | `aura-devtools/` |

---

## Phase 4 — GUI Dashboard ⏳

**Status:** Planned · **ETA:** Week 16

A desktop interface that makes AURA visual.

| Deliverable | Tech | Module |
|---|---|---|
| Main dashboard window | PyQt6 | `aura-gui/` |
| Live command log panel | PyQt6 | `aura-gui/` |
| System health widget | PyQt6 | `aura-gui/` |
| Voice input toggle + waveform display | PyQt6 | `aura-gui/` |

---

## Phase 5 — Memory Layer ⏳

**Status:** Planned · **ETA:** Week 18

AURA remembers. Persistent semantic context across sessions.

| Deliverable | Tech | Module |
|---|---|---|
| ChromaDB vector store setup | ChromaDB | `aura-memory/` |
| Project context indexer | ChromaDB | `aura-memory/` |
| Semantic codebase search | ChromaDB | `aura-memory/` |
| Conversation history persistence | ChromaDB | `aura-memory/` |

---

## v1.0 Release

When all 5 phases ship, AURA v1.0 is:

- A fully offline, voice-controlled AI developer assistant
- Powered by local LLMs (no cloud, no API keys)
- With Git/Docker automation, a desktop GUI, and persistent memory
- 100% open source under MIT

---

*See [CHANGELOG.md](CHANGELOG.md) for version history.*
