"""Microphone device selection shared by wake word and STT."""

from __future__ import annotations

import logging
import time
from typing import Any

import numpy as np
import sounddevice as sd

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
_PROBE_CHUNK = 1280

# Shared across wake word + STT so both use the same mic after one resolve.
_cached_device: int | None = None


def _device_opens(device_index: int) -> bool:
    """True if we can open a 16 kHz mono stream (same as wake word / STT)."""
    try:
        with sd.InputStream(
            device=device_index,
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=_PROBE_CHUNK,
        ):
            pass
        return True
    except Exception:
        return False


def _probe_device_rms(device_index: int, seconds: float = 0.35) -> float:
    rms_max = 0.0
    try:
        with sd.InputStream(
            device=device_index,
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=_PROBE_CHUNK,
        ) as stream:
            deadline = time.time() + seconds
            while time.time() < deadline:
                data, _ = stream.read(_PROBE_CHUNK)
                rms = float(np.sqrt(np.mean(data**2)))
                rms_max = max(rms_max, rms)
    except Exception:
        return 0.0
    return rms_max


def resolve_input_device(config: dict[str, Any] | Any, *, force: bool = False) -> int:
    """
    Return the mic index to use. Honors wake_word.input_device when set;
    otherwise picks the device with the strongest signal (fixes Windows
    defaulting to a dead 'External Microphone').
    """
    global _cached_device

    ww = config.get("wake_word", {}) if isinstance(config, dict) else {}
    explicit = ww.get("input_device")
    if explicit is not None:
        idx = int(explicit)
        if not _device_opens(idx):
            logger.warning(
                "[Audio] Configured input_device [%d] cannot be opened — "
                "check index in config.yaml (run scripts/check_aura_voice.py)",
                idx,
            )
        _cached_device = idx
        return idx

    if _cached_device is not None and not force:
        return _cached_device

    default_in = sd.default.device[0]
    if default_in is None or default_in < 0:
        default_in = 0
    else:
        default_in = int(default_in)

    if _device_opens(default_in):
        default_rms = _probe_device_rms(default_in, seconds=0.35)
        if default_rms >= 0.002:
            _cached_device = default_in
            return default_in
    else:
        default_rms = 0.0
        logger.warning(
            "[Audio] Windows default mic [%d] cannot be opened — scanning alternatives",
            default_in,
        )

    best_idx = default_in
    best_rms = default_rms
    for i, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] <= 0 or i == default_in:
            continue
        if not _device_opens(i):
            continue
        rms = _probe_device_rms(i, seconds=0.2)
        if rms > best_rms:
            best_rms = rms
            best_idx = i

    if not _device_opens(best_idx):
        logger.error(
            "[Audio] No working microphone found — set wake_word.input_device in config.yaml"
        )
    elif best_rms < 0.0005:
        logger.warning(
            "[Audio] All probed mics very quiet (peak rms %.6f). "
            "Check Windows Settings → Privacy → Microphone for Python.",
            best_rms,
        )
    elif best_idx != default_in:
        logger.info(
            "[Audio] Auto-selected mic [%d] (rms %.4f) — Windows default [%d] was weaker",
            best_idx,
            best_rms,
            default_in,
        )

    _cached_device = best_idx
    return best_idx
