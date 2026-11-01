
<div align="center">

# Locus

### A private, offline-first assistant for your PC

**Type or speak a command. Locus does it, on your machine, without sending anything to the cloud.**

[![Latest release](https://img.shields.io/github/v/release/aryanjsx/Locus?label=release)](https://github.com/aryanjsx/Locus/releases/latest)
[![PyPI](https://img.shields.io/pypi/v/locus-assistant)](https://pypi.org/project/locus-assistant/)
![Status](https://img.shields.io/badge/status-alpha-orange)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-0078D6)
![License](https://img.shields.io/github/license/aryanjsx/Locus)
[![XERJ Corpus Hub contributor](https://hub.xerj.org/contributors/aryanjsx/badge.svg)](https://hub.xerj.org/contributors/aryanjsx)


**[Download for Windows, macOS or Linux](https://aryanjsx.github.io/Locus/#download)**

[Website](https://aryanjsx.github.io/Locus/) · [Why Locus](#why-locus) · [What it can do](#what-locus-can-do) · [Install](#installation) · [Quick start](#quick-start) · [Privacy](#privacy) · [Docs](https://aryanjsx.github.io/Locus/getting-started/installation/)

</div>

## Why Locus?

Personal AI agents are exploding in popularity, but nearly all of them still route intelligence through cloud APIs. Your "personal" AI continues to depend on someone else's server. At the same time, [Intelligence Per Watt](https://www.intelligence-per-watt.ai/) research from Stanford's Hazy Research showed that local language models already handle 88.7% of single-turn chat and reasoning queries, with intelligence efficiency improving 5.3× from 2023 to 2025. The models and hardware are increasingly ready. What has been missing is the software stack to make local-first personal AI practical.

Locus is that stack. It is a framework for local-first personal AI, built around three core ideas: shared primitives for building on-device agents; evaluations that treat energy, FLOPs, latency, and dollar cost as first-class constraints alongside accuracy; and a learning loop that improves models using local trace data. The goal is simple: make it possible to build personal AI agents that run locally by default, calling the cloud only when truly necessary. Locus aims to be both a research platform and a production foundation for local AI, in the spirit of PyTorch.

## What Locus can do

- **Chat on your PC:** talk to a local AI model in the desktop app, your browser, or the terminal, by typing or by voice.
- **Attach files and images:** drop documents (PDF, Word, Excel, PowerPoint, OpenDocument, EPUB, HTML, CSV, code, plain text and more) or images into a chat and ask about them. Images need a vision model such as `qwen3.5` or `gemma3`.
- **Search the web:** turn on **Web search** and Locus looks up your question online first, reads the top pages, and answers with numbered links to its sources. It's off until you turn it on, since it sends your question to a search engine.
- **Work with your files:** read and write files and PDFs, search your own documents, run code in a sandbox, and remember facts between conversations.
- **Connect your apps:** Gmail, Outlook, Google Calendar, Google Drive, Dropbox, Notion, Obsidian, GitHub, Slack and more, each only after you sign in.
- **Reply on messaging apps:** run it as a bot on Telegram, Slack, Discord, WhatsApp, Teams, Signal, email, SMS and about 25 other channels.
- **Do tasks on its own:** deep research reports, a daily morning digest, and agents that run on a schedule.
- **Measure itself:** dashboards for energy use, speed, cost savings compared with cloud AI, and step-by-step traces of each answer.
- **Run the AI your way:** Ollama (bundled with the desktop app), llama.cpp, vLLM, or Apple's on-device models, plus optional cloud models with your own API key.

## Installation

### Desktop app

The easiest way is the **[download button on the website](https://aryanjsx.github.io/Locus/#download)**. It detects your system and downloads the right installer directly. You can also pick a file from the [latest release](https://github.com/aryanjsx/Locus/releases/latest):

| Platform | File |
|---|---|
| **Windows 10 and 11 (64-bit)** | `Locus_<version>_x64-setup.exe` or `Locus_<version>_x64_en-US.msi` |
| **Windows 11 on ARM** | `Locus_<version>_arm64-setup.exe` |
| **macOS 10.15 or later (Apple silicon and Intel)** | `Locus_<version>_universal.dmg` |
| **Linux (x86-64)** | `Locus_<version>_amd64.AppImage`, `.deb`, or `.rpm` |

8 GB of memory is enough for a small model; 16 GB runs noticeably better ones. A graphics card helps but isn't required.

On first launch, choose **Ollama** to run models on your PC (or point Locus at your own OpenAI-compatible server). Locus then sets itself up: it installs its private Python runtime, starts the bundled Ollama, and downloads a model sized for your RAM. You don't need to install git, Python, Rust, or Ollama yourself. First launch needs an internet connection and takes a few minutes; later launches start in seconds.

The desktop app checks for new releases and offers to install them.

> [!NOTE]
> The installers aren't code-signed yet, so your OS warns you on first launch.
> - **Windows:** if SmartScreen blocks the installer, choose **More info → Run anyway**.
> - **macOS:** right-click **Locus.app** and choose **Open**, or allow it in **System Settings → Privacy & Security**. If macOS says the app is damaged, run `xattr -cr /Applications/Locus.app`.

### Command line

Pick your platform and run one command. Each installer handles [uv](https://docs.astral.sh/uv/), the Python venv, Ollama, and a starter model, in about 3 minutes on broadband.

| Platform | One-liner |
|---|---|
| **macOS · Linux · WSL2** | `curl -fsSL https://aryanjsx.github.io/Locus/install.sh \| bash` |
| **Native Windows (PowerShell)** | `irm https://aryanjsx.github.io/Locus/install.ps1 \| iex` |

Then run `locus` to start. The Rust extension and larger models continue downloading in the background; `locus doctor` shows status.

### Python package

Locus is also on PyPI as [`locus-assistant`](https://pypi.org/project/locus-assistant/). It needs Python 3.10–3.13 and a running [Ollama](https://ollama.com/):

```bash
pip install locus-assistant
```

The package installs the `locus` command; the Python import name is `locus`.

Platform-specific notes (WSL2 setup, native-Windows scheduled-task service, desktop prerequisites, manual and contributor installs): see the [installation docs](https://aryanjsx.github.io/Locus/getting-started/install/).

## Quick start

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

### Built-in agents

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

Full documentation—including Docker deployment, cloud engines, development setup, and tutorials—is at **[aryanjsx.github.io/Locus](https://aryanjsx.github.io/Locus/)**.

## Privacy

- **Local by default:** models run on your machine through Ollama or another local engine. Nothing goes to a cloud model unless you add your own API key.
- **No analytics:** Locus ships with no analytics destination, so no usage data is sent anywhere. See [telemetry](https://aryanjsx.github.io/Locus/telemetry/) for details.
- **Attachments stay local:** attached files are read by Locus on your machine and kept in the app's own storage. Web search is off by default; when you turn it on, only your question goes to the search engine, never your files.
- **Opt-in connections:** email, calendar, messaging and other services only work after you connect them, and the data you index stays on your machine.
- **Approval for risky actions:** shell commands and similar tools go through an approval step first.

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
