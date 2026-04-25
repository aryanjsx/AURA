# AURA — Phase Layouts

Authoritative list of what each phase ships and where it lives inside
the package.  Folder names are final; they are created under `aura/`
as each phase opens — no more root-level `aura-*/` placeholders that
collide with `aura.core`, `aura.runtime`, and `aura.security`.

See [`../ROADMAP.md`](../ROADMAP.md) for schedule, status, and
deliverables.

**Current state:**

- Phase 0 — Project Core (INFRA) — **COMPLETED**
- Phase 1 — Foundation (System Plugin) — **COMPLETED**
- Phase 2 — Voice + Intelligence Router — **IN PROGRESS** (this document's active section)
- Phase 3 — Dev Tools (Git + Docker) — Planned
- Phase 4 — Vision (Screen Understanding) — Planned
- Phase 5 — GUI Dashboard — Planned
- Phase 6 — Memory + RAG — Planned
- Phase 7 — Browser Automation — Planned
- Phase 8 — Integrations — Planned

---

## Phase 2 — Voice + Intelligence Router

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

## Phase 3 — Dev Tools (Git + Docker)

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
└── docker/
    ├── plugin.py
    └── executor.py        # Docker SDK wrapper
```

Every new action must be declared in `plugins_manifest.yaml` before
registration; the worker enforces the SHA-256 manifest binding.

---

## Phase 4 — Vision (Screen Understanding)

**Status:** Planned.  AURA sees your screen.

| Component         | Technology       | Purpose                                    |
|-------------------|------------------|--------------------------------------------|
| Screen Capture    | Pillow / mss     | Grab screenshots programmatically          |
| OCR               | Tesseract        | Extract text from screen regions           |
| Visual Reasoning  | LLaVA (local)    | Answer questions about what's on screen    |

Planned layout:

```
plugins/vision/
├── plugin.py
├── capture.py           # Screenshot acquisition
├── ocr.py               # Tesseract text extraction
└── reasoning.py         # LLaVA visual question answering
```

---

## Phase 5 — GUI Dashboard

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

## Phase 6 — Memory + RAG

**Status:** Planned.  Persistent semantic project context.

| Component       | Technology       | Purpose                                          |
|-----------------|------------------|--------------------------------------------------|
| Vector Store    | ChromaDB         | Persistent local embedding storage               |
| Project Indexer | nomic-embed-text | Index codebase files and project structure       |
| Semantic Search | ChromaDB         | Query project context by meaning                 |
| History         | ChromaDB         | Conversation and action history across sessions  |

Planned layout:

```
plugins/memory/
├── plugin.py
├── store.py             # ChromaDB collection management
├── indexer.py           # Project file and codebase indexer
├── search.py            # Semantic similarity search
└── history.py           # Conversation / action log persistence
```

---

## Phase 7 — Browser Automation

**Status:** Planned.  Sandboxed web automation.

| Component       | Technology | Purpose                                      |
|-----------------|------------|----------------------------------------------|
| Browser Control | Playwright | Headless browser automation                  |
| Web Research    | Playwright | Search, scrape, and summarise web pages      |
| Form Filling    | Playwright | Automated form submission                    |

Planned layout:

```
plugins/browser/
├── plugin.py
├── controller.py        # Playwright session management
├── research.py          # Web search and scraping pipeline
└── forms.py             # Form detection and auto-fill
```

---

## Phase 8 — Integrations

**Status:** Planned.  Optional bridges to services you trust.

| Component  | Technology        | Purpose                          |
|------------|-------------------|----------------------------------|
| Spotify    | Local Spotify API | Music playback control           |
| Weather    | Weather API       | Local weather data               |
| Calendar   | CalDAV / local    | Schedule and event management    |
| Gmail      | IMAP / local      | Email reading and management     |

Planned layout:

```
plugins/
├── spotify/
│   └── plugin.py
├── weather/
│   └── plugin.py
├── calendar/
│   └── plugin.py
└── gmail/
    └── plugin.py
```

All integrations are entirely opt-in and never enabled by default.

---

Contributions for each phase open when its predecessor ships.  See
[`../CONTRIBUTING.md`](../CONTRIBUTING.md).
