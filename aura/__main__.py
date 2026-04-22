"""Entry point for ``python -m aura``.

Keeping the launcher this thin lets the real CLI code live in
:mod:`aura.cli` and stay importable by tests (e.g. the lockdown suite
imports :func:`bootstrap`) without triggering ``if __name__ == '__main__'``
side effects.
"""
from __future__ import annotations

from aura.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
