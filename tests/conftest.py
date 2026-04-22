"""Pytest bootstrap: ensure repo root is importable and config is loaded once."""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from aura.core.config_loader import load_config  # noqa: E402

load_config()
