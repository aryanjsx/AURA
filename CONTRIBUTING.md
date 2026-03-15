# 🤝 Contributing to AURA

First off — thank you for considering contributing to AURA! Whether it's fixing a typo, proposing a feature, or building an entire module, every contribution moves the project forward.

AURA is a fully offline AI developer assistant. We value clean code, clear documentation, and a welcoming community.

---

## Getting Started

### 1. Fork and Clone

```bash
git clone https://github.com/<your-username>/AURA.git
cd AURA
pip install -r requirements.txt
```

### 2. Create a Branch

Always branch from `main`. Use the naming conventions below.

```bash
git checkout -b feat/your-feature-name
```

### 3. Make Your Changes

- Keep each module independent — no cross-dependencies between modules
- Add docstrings to all public functions
- Include error handling
- Test locally (offline — no network calls)

### 4. Commit Your Changes

We follow [Conventional Commits](https://www.conventionalcommits.org/).

**Format:** `type(module): short description`

```
feat(aura-core): add subprocess command dispatcher
fix(aura-devtools): resolve git push auth error
docs(readme): update architecture diagram
chore(.github): add PR template
test(aura-core): add unit tests for file operations
refactor(command_engine): simplify dispatcher routing
```

**Types:** `feat` · `fix` · `docs` · `chore` · `test` · `refactor` · `style`

### 5. Push and Open a PR

```bash
git push origin feat/your-feature-name
```

Then open a Pull Request against `main`. Fill out the [PR template](.github/PULL_REQUEST_TEMPLATE.md) — it takes 30 seconds and helps reviewers understand your change.

---

## Branch Naming Conventions

| Branch Type | Pattern | Example |
|---|---|---|
| Feature | `feat/module-description` | `feat/whisper-stt-integration` |
| Bug fix | `fix/module-description` | `fix/git-push-auth` |
| Documentation | `docs/description` | `docs/architecture-update` |
| Experiment | `exp/description` | `exp/llama-prompt-tuning` |

---

## Where to Contribute

Each module has a clear home in the codebase:

| Module | Directory | Description |
|---|---|---|
| Command Engine | `command_engine/` | Dispatcher, file ops, process control, system checks |
| Utilities | `modules/` | Project scaffolder, log reader |
| Core Pipeline | `aura-core/` | *(Phase 2)* Whisper STT, Ollama LLM, Piper TTS |
| Dev Tools | `aura-devtools/` | *(Phase 3)* GitPython, Docker SDK |
| GUI | `aura-gui/` | *(Phase 4)* PyQt6 dashboard |
| Memory | `aura-memory/` | *(Phase 5)* ChromaDB vector store |
| Documentation | `docs/` | Architecture docs, guides |

### Currently Accepting Contributions

#### Phase 1 — Now
- Python automation module testing
- Documentation improvements
- `.gitignore` and project config refinements
- Bug reports and fixes

#### Phase 2 — Opening Soon
- Whisper STT integration and optimization
- Ollama prompt engineering for developer tasks
- Piper TTS voice configuration

#### Phase 3+ — Future
- Git automation edge cases
- Docker SDK integration
- PyQt6 dashboard components
- ChromaDB memory schema design

---

## Coding Standards

- **Python 3.10+** — use type hints and `from __future__ import annotations`
- **Docstrings** on all public functions (NumPy-style)
- **Error handling** — never let exceptions propagate silently
- **No cloud dependencies** — everything must work fully offline
- **No hardcoded secrets** — use environment variables
- **Modular design** — each file should be independently importable

---

## Reporting Issues

- Use the [Bug Report](https://github.com/aryanjsx/AURA/issues/new?template=bug_report.md) template for bugs
- Use the [Feature Request](https://github.com/aryanjsx/AURA/issues/new?template=feature_request.md) template for ideas
- Use the [Module Proposal](https://github.com/aryanjsx/AURA/issues/new?template=module_proposal.md) template to propose a new AURA module

Want to claim an issue? Comment "I'd like to work on this" and we'll assign it to you.

---

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to uphold a welcoming, respectful, and harassment-free environment.

---

Thank you for helping build the future of offline AI dev tools. ⚡
