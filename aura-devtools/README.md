# aura-devtools

> Git and Docker automation for developers.

**Status:** Planned (Phase 3)

This module will automate real developer workflows — version control and container management — from text or voice commands.

| Component | Technology | Purpose |
|---|---|---|
| Git Automation | GitPython | Commit, push, branch, status, AI commit messages |
| Docker Management | Docker SDK | Build, run, stop, inspect containers |

## Planned Structure

```
aura-devtools/
├── git_manager.py        # GitPython automation
├── docker_manager.py     # Docker SDK lifecycle management
└── commit_generator.py   # AI-powered commit message generation (via Ollama)
```

## Contributing

This module is opening for contributions when Phase 3 begins. See [CONTRIBUTING.md](../CONTRIBUTING.md) for guidelines.
