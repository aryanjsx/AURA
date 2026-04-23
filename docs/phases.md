# AURA — Phase Layouts

Authoritative list of what each phase ships and where it lives inside
the package.  Folder names are final; they are created under `aura/`
as each phase opens — no more root-level `aura-*/` placeholders that
collide with `aura.core`, `aura.runtime`, and `aura.security`.

See [`../ROADMAP.md`](../ROADMAP.md) for schedule, status, and
deliverables.

**Current state:**

- Phase 0 — Core Infrastructure — **COMPLETED**
- Phase 1 — Python Automation Core + Secure Execution — **COMPLETED**
- Phase 2 — Offline Voice Pipeline — **IN PROGRESS** (this document's active section)
- Phase 3–5 — Planned

---

## Phase 2 — Offline Voice Pipeline / Intelligence Layer

**Status:** IN PROGRESS.  Hear, think, speak — fully local.

| Component       | Technology         | Purpose                                  |
|-----------------|--------------------|------------------------------------------|
| Speech-to-Text  | Whisper (OpenAI)   | Transcribe microphone input to text      |
| Intent Parser   | Ollama (Llama 3)   | Translate dev intent into `Intent` calls |
| Text-to-Speech  | Piper TTS          | Speak results back to the user           |

Planned layout:

```
aura/voice/
├── stt.py              # Whisper microphone listener (InputSource)
├── llm.py              # Ollama prompt engineering + intent emitter
├── tts.py              # Piper voice synthesis (OutputSink)
└── pipeline.py         # End-to-end: hear -> think -> speak
```

The STT and TTS modules plug into the existing `aura.core.io.InputSource`
/ `OutputSink` contracts — no changes to the router or registry.

---

## Phase 3 — Developer Tools

**Status:** Planned.  Git and Docker automation from voice or text.

| Component         | Technology   | Purpose                                    |
|-------------------|--------------|--------------------------------------------|
| Git Automation    | GitPython    | Commit, push, branch, status, AI messages  |
| Docker Management | Docker SDK   | Build, run, stop, inspect containers       |
| Commit Generator  | Ollama       | AI-powered commit messages                 |

Planned layout — one worker-side plugin per tool:

```
plugins/
├── git/
│   ├── plugin.py
│   └── executor.py        # GitPython wrapper
├── docker/
│   ├── plugin.py
│   └── executor.py        # Docker SDK wrapper
└── ai_commit/
    ├── plugin.py
    └── executor.py        # Ollama-driven commit messages
```

Every new action must be declared in `plugins_manifest.yaml` before
registration; the worker enforces the SHA-256 manifest binding.

---

## Phase 4 — GUI Dashboard

**Status:** Planned.  Desktop-native frontend.

| Component      | Technology | Purpose                                      |
|----------------|------------|----------------------------------------------|
| Dashboard      | PyQt6      | Main application window                     |
| Command Log    | PyQt6      | Live scrolling command + result panel        |
| System Widget  | PyQt6      | Real-time system health display              |
| Voice Toggle   | PyQt6      | Mic input control + waveform visualiser      |

Planned layout:

```
aura/gui/
├── main_window.py       # Application entry point
├── widgets/
│   ├── command_log.py   # Live command history panel
│   ├── health_bar.py    # System health status widget
│   └── voice_input.py   # Mic toggle + waveform display
└── styles/
    └── theme.qss        # Qt stylesheet
```

The GUI is an additional frontend: it drives the same `Router` that the
CLI uses (a new `InputSource` / `OutputSink` pair).  The execution
pipeline is unchanged.

---

## Phase 5 — Memory Layer

**Status:** Planned.  Persistent semantic project context.

| Component       | Technology | Purpose                                          |
|-----------------|------------|--------------------------------------------------|
| Vector Store    | ChromaDB   | Persistent local embedding storage               |
| Project Indexer | ChromaDB   | Index codebase files and project structure       |
| Semantic Search | ChromaDB   | Query project context by meaning                 |
| History         | ChromaDB   | Conversation and action history across sessions  |

Planned layout:

```
aura/memory/
├── store.py             # ChromaDB collection management
├── indexer.py           # Project file and codebase indexer
├── search.py            # Semantic similarity search
└── history.py           # Conversation / action log persistence
```

`aura.memory` is consumed by the LLM intent parser (Phase 2) and the
audit chain; it never runs inside the worker subprocess.

---

Contributions for each phase open when its predecessor ships.  See
[`../CONTRIBUTING.md`](../CONTRIBUTING.md).
