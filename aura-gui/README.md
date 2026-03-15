# aura-gui

> Desktop dashboard for AURA.

**Status:** Planned (Phase 4)

This module will provide a visual interface for AURA using PyQt6 — a desktop-native GUI with live feedback.

| Component | Technology | Purpose |
|---|---|---|
| Dashboard | PyQt6 | Main application window |
| Command Log | PyQt6 | Live scrolling command + result panel |
| System Widget | PyQt6 | Real-time system health display |
| Voice Toggle | PyQt6 | Mic input control + waveform visualizer |

## Planned Structure

```
aura-gui/
├── main_window.py       # Application entry point
├── widgets/
│   ├── command_log.py   # Live command history panel
│   ├── health_bar.py    # System health status widget
│   └── voice_input.py   # Mic toggle + waveform display
└── styles/
    └── theme.qss        # Qt stylesheet
```

## Contributing

This module is opening for contributions when Phase 4 begins. See [CONTRIBUTING.md](../CONTRIBUTING.md) for guidelines.
