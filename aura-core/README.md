# aura-core

> Offline voice pipeline — hear, think, speak.

**Status:** Planned (Phase 2)

This module will house the three pillars of AURA's voice interaction:

| Component | Technology | Purpose |
|---|---|---|
| Speech-to-Text | Whisper (OpenAI) | Transcribe microphone input to text |
| Intent Parser | Ollama (Llama 3) | Understand developer intent and generate actions |
| Text-to-Speech | Piper TTS | Speak results back to the user |

## Planned Structure

```
aura-core/
├── stt/              # Whisper microphone listener
├── llm/              # Ollama prompt engineering + intent parser
├── tts/              # Piper voice synthesis
└── pipeline.py       # End-to-end: hear → think → speak
```

## Contributing

This module is opening for contributions when Phase 2 begins. See [CONTRIBUTING.md](../CONTRIBUTING.md) for guidelines.
