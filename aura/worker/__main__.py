"""Entry point: ``python -m aura.worker`` — isolated executor subprocess."""
from __future__ import annotations

import sys

from aura.worker.server import run_worker


if __name__ == "__main__":
    raise SystemExit(run_worker(sys.stdin, sys.stdout, sys.stderr))
