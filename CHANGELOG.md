# Changelog

All notable changes to AURA will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

---

## [2.0.0] — 2026-04-25

### Added

- **`--version` flag** — `python -m aura --version` prints `AURA 2.0.0` and exits
- **`--help` flag** — `python -m aura --help` prints usage via `argparse` and exits
- **`--yes` single-command mode** — `python -m aura --yes "<command>"` runs one command non-interactively and exits
- **Mode indicator** — the REPL banner now shows `Mode: ONLINE` or `Mode: OFFLINE` at startup
- **`create project <path>`** — scaffolds a new project with `src/`, `tests/`, `README.md`, `.gitignore`, `requirements.txt`
- **`show logs <file> [n]`** — tails the last *n* lines of any log file (default 20)
- **Python in system health** — `check system health` now reports Python version as the first entry
- **File-exists warning** — `create file` on an existing path warns instead of silently overwriting
- **Config section validation** — missing required top-level sections in `config.yaml` produce a clear error, not a silent fallback
- **Shell built-in support** — `echo`, `dir`, `type`, `cat`, `ls` are executed with `shell=True` on Windows so built-ins work correctly

### Fixed

- **UnicodeEncodeError crash on Windows** — `sys.stdout` and `sys.stderr` are reconfigured to UTF-8 at startup; child processes inherit `PYTHONUTF8=1`
- **Raw tracebacks on invalid config** — startup errors (bad YAML, missing sections) produce a single clean `[AURA]` line instead of a Python traceback
- **`--yes ""` hangs** — empty or whitespace-only `--yes` input now prints an error and exits immediately
- **Audit log false alarm** — hash-chain verification no longer warns on fresh installs or empty log files
- **JSON logs leaking to stderr** — the `stderr` console handler has been removed; structured JSON logs go to file only
- **`help` broken in `--yes` mode** — REPL built-ins (`help`, `exit`, `quit`) now work in single-command mode
- **Smart keyword paths sandboxed** — `desktop/`, `documents/`, `downloads/`, `home/` now resolve to real OS directories instead of creating literal subdirectories in the sandbox

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
