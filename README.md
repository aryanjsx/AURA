
<div align="center">

# Locus

### A private, offline-first assistant for your PC

**Type or speak a command. Locus does it, on your machine, without sending anything to the cloud.**

![Status](https://img.shields.io/badge/status-alpha-orange)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-0078D6)
![License](https://img.shields.io/github/license/aryanjsx/Locus)
[![XERJ Corpus Hub contributor](https://hub.xerj.org/contributors/aryanjsx/badge.svg)](https://hub.xerj.org/contributors/aryanjsx)


[Website](https://aryanjsx.github.io/Locus/) · [Why Locus](#why-locus) · [MVP scope](#mvp-scope) · [Safety](#safety) · [Requirements](#system-requirements) · [Tech stack](#tech-stack) · [Roadmap](#roadmap) · [Docs](#documentation)

</div>

## Why Locus?

Personal AI agents are exploding in popularity, but nearly all of them still route intelligence through cloud APIs. Your "personal" AI continues to depend on someone else's server. At the same time, [Intelligence Per Watt](https://www.intelligence-per-watt.ai/) research from Stanford's Hazy Research showed that local language models already handle 88.7% of single-turn chat and reasoning queries, with intelligence efficiency improving 5.3× from 2023 to 2025. The models and hardware are increasingly ready. What has been missing is the software stack to make local-first personal AI practical.

Locus is that stack. It is a framework for local-first personal AI, built around three core ideas: shared primitives for building on-device agents; evaluations that treat energy, FLOPs, latency, and dollar cost as first-class constraints alongside accuracy; and a learning loop that improves models using local trace data. The goal is simple: make it possible to build personal AI agents that run locally by default, calling the cloud only when truly necessary. Locus aims to be both a research platform and a production foundation for local AI, in the spirit of PyTorch.

## Installation

Pick your platform and run one command. Each installer handles [uv](https://docs.astral.sh/uv/), the Python venv, Ollama, and a starter model — about 3 minutes on broadband.

| Platform | One-liner |
|---|---|
| **macOS · Linux · WSL2** | `curl -fsSL https://aryanjsx.github.io/Locus/install.sh \| bash` |
| **Native Windows** | `irm https://aryanjsx.github.io/Locus/install.ps1 \| iex` |
| **Desktop GUI** | Download `.exe` / `.dmg` / `.deb` / `.rpm` / `.AppImage` from the [latest release](https://github.com/aryanjsx/Locus/releases) |

Then `locus` to start. The Rust extension and larger models continue downloading in the background; `locus doctor` shows status.

Platform-specific notes (WSL2 setup, native-Windows scheduled-task service, desktop prerequisites, manual / contributor install): see the [installation docs](https://aryanjsx.github.io/Locus/getting-started/install/).

## Quick Start

```bash
locus                          # start chatting (default: chat-simple)
locus gui                      # start the graphical browser interface
locus init --preset <name> --force  # replace config with a starter preset
```

`locus gui` starts the local API server and frontend, then opens the graphical
chat interface in your default browser. It requires Node.js 22+ and is
available from a source checkout; packaged desktop installers are available
from the [latest release](https://github.com/aryanjsx/Locus/releases).

> Prefix `locus ...` with `uv run`, or `source .venv/bin/activate` first.

#### Run from a Windows source checkout

Install [uv](https://docs.astral.sh/uv/), [Node.js 22+](https://nodejs.org/),
and [Ollama](https://ollama.com/), then run these commands from the repository
root in PowerShell:

```powershell
uv sync --extra desktop
Push-Location frontend
npm install
Pop-Location
ollama pull qwen3:0.6b
uv run locus gui
```

If Ollama is not already running, start it in another terminal with
`ollama serve`. The GUI should open in your browser.

To run the test suite from the repository root:

```powershell
uv sync --extra dev
uv run pytest tests/ -v
```

| Preset | What it does |
|---|---|
| `morning-digest-mac` / `morning-digest-linux` / `morning-digest-minimal` | Spoken daily briefing from email, calendar, health, news |
| `deep-research` | Multi-hop research across indexed docs with citations |
| `code-assistant` | Agent with code execution, file I/O, and shell access |
| `scheduled-monitor` | Stateful agent on a schedule with memory |
| `chat-simple` | Lightweight conversation, no tools |

Example:

```bash
locus init --preset morning-digest-mac --force
locus connect gdrive          # one OAuth covers Gmail / Calendar / Tasks
locus digest --fresh          # generate and play your first briefing
```

Per-preset deep dives: [morning digest](https://aryanjsx.github.io/Locus/user-guide/morning-digest/) · [deep research](https://aryanjsx.github.io/Locus/user-guide/deep-research/) · [code assistant](https://aryanjsx.github.io/Locus/user-guide/code-assistant/) · [scheduled monitor](https://aryanjsx.github.io/Locus/user-guide/scheduled-monitor/) · [chat simple](https://aryanjsx.github.io/Locus/user-guide/chat-simple/) · or the full [quickstart guide](https://aryanjsx.github.io/Locus/getting-started/quickstart/).

### Skills

Skills teach agents how to better use tools and improve their reasoning. Every skill is a tool — agents discover them from a catalog and invoke them on demand.

```bash
# Install skills from public sources
locus skill install hermes:arxiv
locus skill sync hermes --category research

# Use skills with any agent
locus ask "Use the code-explainer skill to explain this Python code: for i in range(5): print(i*2)"

# Optimize skills from your trace history
locus optimize skills --policy dspy

# Benchmark the impact
locus bench skills --max-samples 5 --seeds 42
```

Import from [Hermes Agent](https://github.com/NousResearch/hermes-agent) (~150 skills), [OpenClaw](https://github.com/openclaw/skills) (~13,700 community skills), or any GitHub repo. Skills follow the [agentskills.io](https://agentskills.io/specification) open standard.

See the [Skills User Guide](https://aryanjsx.github.io/Locus/user-guide/skills/) and [Skills Tutorial](https://aryanjsx.github.io/Locus/tutorials/skills-workflow/) for details.

### Built-in Agents

Locus ships with eight built-in agents across three execution modes (on-demand, scheduled, continuous):

| Agent | Type | What it does |
|-------|------|-------------|
| `morning_digest` | Scheduled | Daily briefing from email, calendar, health, news — with TTS audio |
| `deep_research` | On-demand | Multi-hop research with citations across web and local docs |
| `monitor_operative` | Continuous | Long-horizon monitoring with memory, compression, and retrieval |
| `orchestrator` | On-demand | Multi-turn reasoning with automatic tool selection |
| `native_react` | On-demand | ReAct (Thought-Action-Observation) loop agent |
| `operative` | Continuous | Persistent autonomous agent with state management |
| `native_openhands` | On-demand | CodeAct — generates and executes Python code |
| `simple` | On-demand | Single-turn chat, no tools |

See the [User Guide](https://aryanjsx.github.io/Locus/user-guide/morning-digest/) and [Tutorials](https://aryanjsx.github.io/Locus/tutorials/) for detailed setup instructions.

Full documentation — including Docker deployment, cloud engines, development setup, and tutorials — at **[aryanjsx.github.io/Locus](https://aryanjsx.github.io/Locus/)**.

## Community

- **GitHub:** [github.com/aryanjsx/Locus](https://github.com/aryanjsx/Locus)
- **Discussions:** [github.com/aryanjsx/Locus/discussions](https://github.com/aryanjsx/Locus/discussions)
- **Docs:** [aryanjsx.github.io/Locus](https://aryanjsx.github.io/Locus/)

## Contributing

We welcome contributions! See the [Contributing Guide](CONTRIBUTING.md) for incentives, contribution types, and the PR process.

Quick start for contributors:

```bash
git clone https://github.com/aryanjsx/Locus.git
cd Locus
uv sync --extra dev
uv run pre-commit install
uv run pytest tests/ -v
```

Browse the [Roadmap](https://aryanjsx.github.io/Locus/development/roadmap/) for areas where help is needed. Comment **"take"** on any issue to get auto-assigned.

## Acknowledgments

Locus is a modified version of [OpenJarvis](https://github.com/open-jarvis/OpenJarvis), an open-source framework for local-first personal AI developed at [Hazy Research](https://hazyresearch.stanford.edu/) and the [Scaling Intelligence Lab](https://scalingintelligence.stanford.edu/) at [Stanford SAIL](https://ai.stanford.edu/) as part of [Intelligence Per Watt](https://www.intelligence-per-watt.ai/). OpenJarvis is licensed under Apache 2.0; see [NOTICE](NOTICE) for details. Locus is an independent project and is not affiliated with or endorsed by Stanford or the OpenJarvis authors.

If you use the underlying research, please cite the OpenJarvis paper:

```bibtex
@misc{saadfalcon2026openjarvispersonalaipersonal,
      title={OpenJarvis: Personal AI, On Personal Devices}, 
      author={Jon Saad-Falcon and Avanika Narayan and Robby Manihani and Tanvir Bhathal and Herumb Shandilya and Hakki Orhun Akengin and Gabriel Bo and Andrew Park and Matthew Hart and Caia Costello and Chuan Li and Christopher Ré and Azalia Mirhoseini},
      year={2026},
      eprint={2605.17172},
      archivePrefix={arXiv},
      primaryClass={cs.LG},
      url={https://arxiv.org/abs/2605.17172}, 
}
```

## License

[Apache 2.0](LICENSE)
