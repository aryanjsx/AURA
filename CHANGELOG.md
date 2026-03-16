# Changelog

All notable changes to AURA will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

---

## [0.2.0] — 2026-03-16

### Added

- **Centralized Path Resolution** (`command_engine/path_utils.py`) — single source of truth for converting user paths into safe absolute paths
- **Smart Location Keywords** — `desktop/`, `downloads/`, `documents/` automatically expand to the correct OS directory
- **Path Safety Validation** — protected system directories (e.g. `C:\Windows`, `/usr`) are blocked from destructive operations
- **Tilde Expansion** — `~/Desktop/file.txt` resolves correctly on all platforms

### Changed

- **file_manager.py** — all 5 functions (`create_file`, `delete_file`, `rename_file`, `move_file`, `search_files`) now use `resolve_path()` instead of raw `Path().resolve()`
- **project_scaffolder.py** — `create_project()` accepts full paths (e.g. `~/Desktop/my_app`) instead of only bare names
- **log_reader.py** — `read_last_lines()` resolves file paths through `resolve_path()`
- **dispatcher.py** — improved path parsing for multi-argument commands (`move file`, `rename file`, `show logs`); correctly splits two-path commands using path-boundary heuristics

---

## [0.1.0] — 2026-03-16

### Added

- Command Execution Engine with text-based CLI dispatcher
- File Manager — create, delete, rename, move, glob-search files with pathlib
- Process Manager — run shell commands, list processes, kill by name via psutil
- System Health Check — probe Python, Git, Node, Docker availability
- Smart path resolution — `~`, `desktop/`, `downloads/`, `documents/` keywords via centralized path_utils
- Path Safety — protected system directory blocklist
- Project Scaffolder — generate new project directory skeleton
- Log Reader — tail any log file
- Structured logging to `logs/aura.log` via stdlib logging
- Full GitHub repo scaffolding — issue templates, PR template, CI workflow, CONTRIBUTING, SECURITY
