"""Mode monitor — tracks online/offline state for the intelligence router."""

from __future__ import annotations

import httpx


class ModeMonitor:
    def __init__(self) -> None:
        self.online = False

    def is_online(self) -> bool:
        try:
            httpx.get("https://1.1.1.1", timeout=2)
            self.online = True
        except Exception:
            self.online = False
        return self.online
