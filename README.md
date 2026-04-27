<div align="center">

<img src="docs/assets/AURA.jpg" alt="AURA" width="800"/>

# AURA

### Your computer already has an AI. It just doesn't know it yet.

**Not another chatbot.** AURA is a system-level AI that lives on your machine, executes real actions, and never phones home.

![Build Status](https://github.com/aryanjsx/AURA/actions/workflows/ci.yml/badge.svg)
![License](https://img.shields.io/github/license/aryanjsx/AURA)
![Stars](https://img.shields.io/github/stars/aryanjsx/AURA?style=social)
![Issues](https://img.shields.io/github/issues/aryanjsx/AURA)
![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)

**No cloud. No API keys. No subscriptions. No data leaving your machine. Ever.**

[Get Started](#-getting-started) · [What It Can Do](#-what-aura-can-do-today) · [Roadmap](#-roadmap) · [Contribute](#-contributing)

</div>

---

<!-- TODO: Replace with actual demo GIF
![AURA Demo](docs/assets/demo.gif)
-->

## 💡 The Problem

Every "AI assistant" today is a chat window connected to someone else's server.

You type. It responds. That's it.

You can't tell it to **create a file on your desktop**. You can't ask it to **kill a runaway process**. You can't say **"scaffold a new project"** and watch it happen.

ChatGPT can't touch your filesystem. Copilot can't monitor your CPU. AutoGPT burns through API credits and still can't move a file.

**AURA doesn't chat about doing things. It does them.**

---

## 🔥 What Makes AURA Different

| | ChatGPT / Copilot | AutoGPT / AgentGPT | **AURA** |
|---|---|---|---|
| Runs locally | ❌ Cloud-only | ❌ Needs API keys | ✅ **Fully offline** |
| Executes system actions | ❌ Chat only | ⚠️ Unreliable | ✅ **File, process, npm, shell** |
| Privacy | ❌ Data sent to servers | ❌ Data sent to servers | ✅ **Nothing leaves your machine** |
| Security model | N/A | None | ✅ **Sandboxed, audited, policy-enforced** |
| Voice control | ❌ | ❌ | 🔄 **Coming (Whisper + Piper)** |
| Cost | $20/mo+ | API credits | ✅ **Free forever** |
| Works offline | ❌ | ❌ | ✅ **100% offline capable** |

---

## ⚡ What AURA Can Do Today

> Phase 0 + Phase 1 complete. Everything below works right now.

### File Operations
```
> create file desktop/notes.txt
File created: C:\Users\You\Desktop\notes.txt

> move file desktop/notes.txt documents/notes.txt
Moved: C:\Users\You\Desktop\notes.txt → C:\Users\You\Documents\notes.txt

> search files . *.py
```

### System Control
```
> cpu
CPU: 23.4%

> ram
Memory: 8.2 GB / 16.0 GB

> kill process chrome
Process 'chrome' terminated.

> check system health
python: 3.14.0 | git: 2.51.1 | node: v22.22.0 | npm: 11.6.1
```

### Project Scaffolding
```
> create project desktop/my-app
Project 'my-app' created at C:\Users\You\Desktop\my-app
  → src/ tests/ README.md .gitignore requirements.txt
```

### Shell Execution (allowlisted)
```
> run command git status
> run command npm install
```

### Smart Path Resolution

| You type | AURA resolves to |
|---|---|
| `desktop/file.txt` | `C:\Users\You\Desktop\file.txt` |
| `~/Documents/file.txt` | `C:\Users\You\Documents\file.txt` |
| `myproject/file.txt` | `~/AURA_SANDBOX/myproject/file.txt` |

Every action is **sandboxed**, **policy-checked**, and **audit-logged**. Protected system paths are blocked. Dangerous commands are denied.

---

## 🎬 Demo

<!-- TODO: Add demo GIF here -->
<!-- ![AURA in action](docs/assets/demo.gif) -->

```
    ___   __  ______  ___
   /   | / / / / __ \/   |
  / /| |/ / / / /_/ / /| |
 / ___ / /_/ / _, _/ ___ |
/_/  |_\____/_/ |_/_/  |_|

Autonomous Unified Response Architecture
  Mode: ONLINE ✅

> create file desktop/hello.txt
File created: C:\Users\You\Desktop\hello.txt

> cpu
CPU: 12.3%

> create project desktop/my-app
Project 'my-app' created at C:\Users\You\Desktop\my-app

> exit
Goodbye.
```

---

## 🧠 Why AURA Exists

The future of AI isn't a browser tab. It's an **operating system layer**.

We believe:
- Your AI should run **where your work happens** — on your machine
- It should **do things**, not just suggest things
- Your data should **never leave your control**
- You shouldn't need a subscription to use intelligence

AURA is building that layer. Starting with developer workflows. Expanding to everything.

---

## 🏗️ Architecture

Clean. Layered. Every component is a standalone module.

```
┌──────────────────────────────────────────────────┐
│                   INPUT LAYER                     │
│         CLI · One-shot · Voice (Phase 2)          │
├──────────────────────────────────────────────────┤
│                 REASONING LAYER                   │
│       Intent Parser · LLM Router (Phase 2)        │
├──────────────────────────────────────────────────┤
│                 SECURITY LAYER                    │
│   Sandbox · Policy · Permissions · Audit Chain    │
├──────────────────────────────────────────────────┤
│                 EXECUTION LAYER                   │
│  Isolated Worker Process · Plugin Registry · IPC  │
├──────────────────────────────────────────────────┤
│                  PLUGIN LAYER                     │
│   File · Process · npm · System · Git · Docker    │
├──────────────────────────────────────────────────┤
│                  OUTPUT LAYER                     │
│       Console · TTS (Phase 2) · GUI (Phase 5)     │
└──────────────────────────────────────────────────┘
```

The main process **never imports plugin code**. Plugins run in an **isolated worker subprocess** communicating over JSON IPC. A compromised plugin cannot touch the host.

---

## 📐 Philosophy

> **"If it needs the internet to think, it's not your AI."**

1. **Local-first** — No cloud dependency. No API keys. Works on airplane mode.
2. **Actions over answers** — AURA doesn't explain how to create a file. It creates the file.
3. **Security is non-negotiable** — Sandboxed execution, tamper-evident audit logs, hash-chained integrity.
4. **Modular by design** — Every capability is a plugin. Add what you need. Remove what you don't.
5. **Developer-owned** — Open source. No telemetry. No tracking. Your machine, your rules.

---

## 🗺️ Roadmap

| Phase | What Ships | Status |
|---|---|---|
| **Phase 0 — Core Infrastructure** | Event bus, config, registry, CLI, execution backbone | ✅ Done |
| **Phase 1 — System Plugin** | File/process/npm operations, sandbox, permissions, audit chain | ✅ Done |
| **Phase 2 — Voice + Intelligence** | Whisper STT, Ollama LLM, Piper TTS, tool orchestration | 🔄 In Progress |
| **Phase 3 — Dev Tools** | Git automation, Docker lifecycle management | ⏳ Planned |
| **Phase 4 — Vision** | Screen capture, OCR, visual reasoning with LLaVA | ⏳ Planned |
| **Phase 5 — GUI Dashboard** | PyQt6 desktop interface with live command log | ⏳ Planned |
| **Phase 6 — Memory + RAG** | ChromaDB semantic memory, conversation history | ⏳ Planned |
| **Phase 7 — Browser Automation** | Sandboxed web research with Playwright | ⏳ Planned |
| **Phase 8 — Integrations** | Spotify, Weather, Calendar, Gmail bridges | ⏳ Planned |

The goal: **a fully autonomous, offline AI layer for your entire operating system.**

---

## 🚀 Getting Started

### Prerequisites

- Python 3.10+

### Install

```bash
git clone https://github.com/aryanjsx/AURA.git
cd AURA
pip install -r requirements.txt
```

### Run

```bash
python -m aura              # Interactive REPL
python -m aura --yes "cpu"  # Single command, no prompts
python -m aura --help       # Usage info
```

That's it. No Docker. No cloud setup. No API keys. Just run it.

### Quick Reference

| Category | Commands |
|---|---|
| **Files** | `create file`, `delete file`, `rename file`, `move file`, `search files` |
| **System** | `cpu`, `ram`, `list processes`, `check system health`, `kill process` |
| **Projects** | `create project <path>` |
| **Shell** | `run command <cmd>` (allowlisted: git, npm, docker, echo) |
| **npm** | `npm install [path]`, `npm run <script>` |
| **Logs** | `show logs <file> [n]` |
| **REPL** | `help`, `exit`, `quit` |

---

## ⭐ Star This Repo

If AURA's vision resonates with you — an AI that **runs locally**, **executes real actions**, and **respects your privacy** — drop a star.

It takes one second and tells us you believe AI should be **owned, not rented**.

[![Star this repo](https://img.shields.io/github/stars/aryanjsx/AURA?style=for-the-badge&logo=github&label=Star%20AURA&color=yellow)](https://github.com/aryanjsx/AURA)

Every star pushes this project forward. Every star says: **"The future of AI is local."**

---

## 🤝 Contributing

We're building something big and we want you in.

1. Fork the repo
2. Create your branch (`git checkout -b feat/amazing-feature`)
3. Commit with [Conventional Commits](https://www.conventionalcommits.org/) (`feat(core): add amazing feature`)
4. Push and open a Pull Request

See [CONTRIBUTING.md](CONTRIBUTING.md) for full guidelines. Check out [open issues](https://github.com/aryanjsx/AURA/issues) — look for `good first issue` and `help wanted`.

**Active areas where we need help:**
- Whisper STT integration (Phase 2)
- Ollama prompt engineering for developer tasks
- Piper TTS voice configuration
- Test coverage expansion
- Documentation improvements

---

## 🔭 The Vision

Today, AURA manages files, monitors processes, and scaffolds projects.

Tomorrow, it will:
- **Hear you** — wake word activation, voice commands, hands-free coding
- **See your screen** — understand what you're looking at, act on visual context
- **Remember everything** — semantic memory across sessions, project-aware context
- **Automate your workflow** — git, Docker, browser research, email, calendar — all through one interface
- **Run your entire dev environment** — from a single, private, local AI

No cloud. No subscription. No compromises.

**This is not a tool. It's the beginning of a new relationship between developers and their machines.**

---

<div align="center">

**AURA — Autonomous Unified Response Architecture**

Built offline. Powered locally. Yours completely.

[GitHub](https://github.com/aryanjsx/AURA) · [Issues](https://github.com/aryanjsx/AURA/issues) · [Contributing](CONTRIBUTING.md) · [Roadmap](ROADMAP.md)

MIT License — Built by [@aryanjsx](https://github.com/aryanjsx)

</div>
