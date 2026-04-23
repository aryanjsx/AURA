# 📋 AURA Roadmap

> A fully offline AI developer assistant — from command-line automation to voice-controlled coding workflows.

---

## Progress at a Glance

- [✔] **Phase 0** — Core Infrastructure (COMPLETED)
- [✔] **Phase 1** — Python Automation Core + Secure Execution (COMPLETED)
- [→] **Phase 2** — Offline Voice Pipeline / Intelligence Layer (IN PROGRESS)
- [ ] Phase 3 — Developer Tools (planned)
- [ ] Phase 4 — GUI Dashboard (planned)
- [ ] Phase 5 — Memory Layer (planned)

---

## Phase 0 — Core Infrastructure ✅

**Status:** COMPLETED

The scaffolding. Cross-cutting infrastructure every later phase depends on — nothing user-facing, everything the rest of the system is built on.

| Deliverable | Module | Status |
|---|---|---|
| Event bus (thread-safe pub/sub) | `aura/core/event_bus.py` | ✅ Done |
| Config loader + env overrides | `aura/core/config_loader.py` | ✅ Done |
| Typed error hierarchy | `aura/core/errors.py` | ✅ Done |
| Structured `CommandResult` | `aura/core/result.py` | ✅ Done |
| `CommandSpec` schema + validator | `aura/core/schema.py` | ✅ Done |
| Parameter schema + size caps | `aura/core/param_schema.py` | ✅ Done |
| Trace-ID context var | `aura/core/tracing.py` | ✅ Done |
| Input / output abstractions | `aura/core/io.py` | ✅ Done |
| Structured JSON logger | `aura/core/logger.py` | ✅ Done |
| Interactive CLI bootstrap | `aura/cli.py` | ✅ Done |

---

## Phase 1 — Python Automation Core + Secure Execution ✅

**Status:** COMPLETED

The foundation. A modular command-execution engine plus the full secure-execution layer — sandbox, permissions, audit chain, non-bypassable registry, isolated worker subprocess.

| Deliverable | Module | Status |
|---|---|---|
| Command dispatcher / router (text → Intent → registry) | `aura/runtime/router.py` | ✅ Done |
| Centralized path resolution (`~`, smart keywords, safety) | `plugins/system/executor.py` | ✅ Done |
| File operations (create, delete, rename, move, search) | `plugins/system/executor.py` | ✅ Done |
| Process management (run, list, kill) | `plugins/system/executor.py` | ✅ Done |
| System health checker (Python, Git, Node, Docker) | `plugins/system/executor.py` | ✅ Done |
| Project scaffolder (supports full paths) | `plugins/system/executor.py` | ✅ Done |
| Log file reader (supports full paths) | `plugins/system/executor.py` | ✅ Done |
| Intent system (text/LLM → structured action) | `aura/core/intent.py` | ✅ Done |
| Non-bypassable command registry | `aura/runtime/command_registry.py` | ✅ Done |
| Plugin loader + manifest enforcement | `aura/runtime/plugin_loader.py`, `aura/security/plugin_manifest.py` | ✅ Done |
| Isolated worker subprocess (JSON-line IPC) | `aura/worker/server.py`, `aura/runtime/worker_client.py` | ✅ Done |
| Filesystem sandbox + symlink escape block | `aura/security/sandbox.py` | ✅ Done |
| Shell argv allowlist + denylist policy | `aura/security/policy.py` | ✅ Done |
| PermissionLevel validator (source-capped) | `aura/security/permissions.py` | ✅ Done |
| Per-source sliding-window rate limiter | `aura/security/rate_limiter.py` | ✅ Done |
| Non-blocking confirmation safety gate | `aura/security/safety_gate.py` | ✅ Done |
| Tamper-evident hash-chained audit log + rotation sidecar | `aura/security/audit_log.py` | ✅ Done |
| Dynamic audit event registry | `aura/security/audit_events.py` | ✅ Done |
| LLM backend abstraction + Ollama stub | `aura/core/backends/` | ✅ Done |
| LLM brain (intent translator stub) | `aura/core/llm_brain.py` | ✅ Done |

Security properties verified end-to-end (runtime-probed, not documented-only):

- Exactly one execution entry point (`CommandRegistry.execute`) — no reachable dispatcher via reflection, closure walk, or `dir()` introspection.
- Worker boundary is JSON-only, size-capped, manifest-hash-bound, and schema-validated in both directions.
- Audit chain distinguishes rotation truncation from tampering via sidecar hash file.

---

## Phase 2 — Offline Voice Pipeline / Intelligence Layer 🔄

**Status:** IN PROGRESS · **ETA:** Week 9

The transformation. AURA hears you, thinks locally, and speaks back.

| Deliverable | Tech | Module |
|---|---|---|
| Microphone listener + speech-to-text | Whisper (OpenAI) | `core/io.py` + new STT source |
| Intent parsing + command generation | Ollama (Llama 3) | `core/llm_brain.py`, `core/backends/` |
| Voice response synthesis | Piper TTS | `core/io.py` + new TTS sink |
| Prompt engineering for dev-task classification | — | `core/llm_brain.py` |
| End-to-end voice → action → response pipeline | — | `aura.py` (async main loop) |

---

## Phase 3 — Developer Tools ⏳

**Status:** Planned · **ETA:** Week 13

Real developer workflow automation — Git and Docker from voice or text.

| Deliverable | Tech | Module |
|---|---|---|
| Git automation (commit, push, branch, status) | GitPython | `plugins/git/` |
| AI-generated commit messages | Ollama | `plugins/ai_commit/` |
| Docker container lifecycle (build, run, stop, logs) | Docker SDK | `plugins/docker/` |

---

## Phase 4 — GUI Dashboard ⏳

**Status:** Planned · **ETA:** Week 16

A desktop interface that makes AURA visual.

| Deliverable | Tech | Module |
|---|---|---|
| Main dashboard window | PyQt6 | `aura/gui/` |
| Live command log panel | PyQt6 | `aura/gui/` |
| System health widget | PyQt6 | `aura/gui/` |
| Voice input toggle + waveform display | PyQt6 | `aura/gui/` |

---

## Phase 5 — Memory Layer ⏳

**Status:** Planned · **ETA:** Week 18

AURA remembers. Persistent semantic context across sessions.

| Deliverable | Tech | Module |
|---|---|---|
| ChromaDB vector store setup | ChromaDB | `aura/memory/` |
| Project context indexer | ChromaDB | `aura/memory/` |
| Semantic codebase search | ChromaDB | `aura/memory/` |
| Conversation history persistence | ChromaDB | `aura/memory/` |

> Phase 2 is the currently active phase. Its code lands inside the existing `aura/` / `plugins/` tree (`aura/voice/` for STT/TTS, tool-orchestration updates to `aura/runtime/`); Phase 3–5 follow the same pattern (`plugins/git/`, `aura/gui/`, `aura/memory/`). Final per-file layout is locked in when each phase opens — see [`docs/phases.md`](docs/phases.md) for the current plan.

---

## v1.0 Release

When all 5 phases ship, AURA v1.0 is:

- A fully offline, voice-controlled AI developer assistant
- Powered by local LLMs (no cloud, no API keys)
- With Git/Docker automation, a desktop GUI, and persistent memory
- 100% open source under MIT

---

*See [CHANGELOG.md](CHANGELOG.md) for version history.*
