# aura-memory

> Persistent semantic memory for AURA.

**Status:** Planned (Phase 5)

This module will give AURA the ability to remember — project context, conversation history, and codebase structure stored as vector embeddings.

| Component | Technology | Purpose |
|---|---|---|
| Vector Store | ChromaDB | Persistent local embedding storage |
| Project Indexer | ChromaDB | Index codebase files and project structure |
| Semantic Search | ChromaDB | Query project context by meaning |
| History | ChromaDB | Conversation and action history across sessions |

## Planned Structure

```
aura-memory/
├── store.py             # ChromaDB collection management
├── indexer.py           # Project file and codebase indexer
├── search.py            # Semantic similarity search
└── history.py           # Conversation and action log persistence
```

## Contributing

This module is opening for contributions when Phase 5 begins. See [CONTRIBUTING.md](../CONTRIBUTING.md) for guidelines.
