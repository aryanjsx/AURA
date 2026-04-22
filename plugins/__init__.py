"""
AURA plugins root package.

Hardening guard
---------------
Plugin executor code is only allowed to load inside the isolated
:mod:`aura.worker` subprocess.  The main process never needs to touch
``plugins.*`` — all interaction happens via JSON IPC — so any attempt
to import a plugin from a non-worker process is refused at import
time.

The sentinel is :envvar:`AURA_WORKER` (set by
:class:`aura.runtime.worker_client.WorkerClient` before spawning).  An
attacker who already has Python-code execution in the main process
could forge the variable, so this is defence-in-depth, not a bright
line — the actual security boundary is the subprocess itself and the
JSON-only IPC channel.
"""
from __future__ import annotations

import os

if os.environ.get("AURA_WORKER") != "1":
    raise RuntimeError(
        "plugins.* may only be imported from the isolated AURA worker "
        "(AURA_WORKER=1).  If you see this in the main process, the "
        "code path is attempting to bypass the WorkerClient IPC boundary."
    )
