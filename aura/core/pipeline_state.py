"""
AURA — Pipeline State Machine (Phase 2).

Enforces that only one pipeline state is active at any time.
All state transitions go through this class — callers never set
state directly.

Thread-safe: uses a lock around every transition so concurrent
event handlers cannot corrupt the state.
"""

from __future__ import annotations

import logging
import threading
from enum import Enum, auto

logger = logging.getLogger("aura.pipeline_state")


class PipelineState(Enum):
    IDLE        = auto()
    LISTENING   = auto()
    CLASSIFYING = auto()
    THINKING    = auto()
    EXECUTING   = auto()
    SPEAKING    = auto()


class StateMachine:
    """
    Enforces that only one pipeline state is active at any time.
    All state transitions go through this class.
    """

    VALID_TRANSITIONS: dict[PipelineState, list[PipelineState]] = {
        PipelineState.IDLE:        [PipelineState.LISTENING],
        PipelineState.LISTENING:   [PipelineState.CLASSIFYING, PipelineState.IDLE],
        PipelineState.CLASSIFYING: [PipelineState.THINKING, PipelineState.IDLE],
        PipelineState.THINKING:    [PipelineState.EXECUTING, PipelineState.SPEAKING, PipelineState.IDLE],
        PipelineState.EXECUTING:   [PipelineState.SPEAKING, PipelineState.IDLE],
        PipelineState.SPEAKING:    [PipelineState.IDLE],
    }

    def __init__(self) -> None:
        self._state = PipelineState.IDLE
        self._lock = threading.Lock()

    @property
    def current(self) -> PipelineState:
        return self._state

    def transition(self, new_state: PipelineState) -> bool:
        """Attempt a state transition. Returns True if successful."""
        with self._lock:
            allowed = self.VALID_TRANSITIONS.get(self._state, [])
            if new_state not in allowed:
                logger.debug(
                    "Invalid transition %s → %s (allowed: %s)",
                    self._state.name, new_state.name,
                    [s.name for s in allowed],
                )
                return False
            old = self._state
            self._state = new_state
            logger.debug("State: %s → %s", old.name, new_state.name)
            return True

    def force_idle(self) -> None:
        """Force state to IDLE (error recovery)."""
        with self._lock:
            self._state = PipelineState.IDLE
            logger.info("State force-reset to IDLE")
