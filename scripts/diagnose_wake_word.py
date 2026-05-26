"""
Live wake-word diagnostic — run while saying "Hey Jarvis".

  python scripts/diagnose_wake_word.py

Shows mic level and hey_jarvis scores every second. Press Ctrl+C to stop.
"""

from __future__ import annotations

import sys
import time

import numpy as np
import sounddevice as sd

from aura.core.config_loader import load_config


def main() -> None:
    config = load_config()
    ww = config.get("wake_word", {})
    model_name = ww.get("oww_model", "hey_jarvis")
    threshold = float(ww.get("oww_threshold", 0.35))
    patience = int(ww.get("oww_patience", 2))
    chunk_ms = int(ww.get("oww_chunk_ms", 80))
    device = ww.get("input_device")

    from openwakeword.model import Model
    from openwakeword.utils import download_models
    import openwakeword
    import os

    models_dir = os.path.join(
        os.path.dirname(openwakeword.__file__), "resources", "models"
    )
    if not os.path.isfile(os.path.join(models_dir, f"{model_name}_v0.1.onnx")):
        print("Downloading openwakeword models (first run only)...")
        download_models()

    framework = "onnx"
    try:
        import tflite_runtime  # noqa: F401
        framework = "tflite"
    except ImportError:
        pass

    oww = Model(wakeword_models=[model_name], inference_framework=framework)

    sr = 16000
    chunk_samples = int(sr * chunk_ms / 1000)
    inp, outp = sd.default.device
    print(f"Default devices: input={inp} output={outp}")
    if device is not None:
        print(f"Using config input_device={device}")
    else:
        print("Tip: set wake_word.input_device in config.yaml if wrong mic is used")
    print(f"Model={model_name} framework={framework} threshold={threshold} patience={patience}")
    print('Say "Hey Jarvis" clearly, then pause. Ctrl+C to exit.\n')
    patience_map = {model_name: patience}
    threshold_map = {model_name: threshold}

    stream_kwargs = dict(
        samplerate=sr, channels=1, dtype="float32", blocksize=chunk_samples
    )
    if device is not None:
        stream_kwargs["device"] = int(device)

    max_score = 0.0
    last_print = 0.0

    with sd.InputStream(**stream_kwargs) as stream:
        while True:
            chunk, _ = stream.read(chunk_samples)
            flat = chunk.flatten()
            rms = float(np.sqrt(np.mean(flat**2)))
            pcm = (np.clip(flat, -1.0, 1.0) * 32767).astype(np.int16)
            pred = oww.predict(
                pcm, patience=patience_map, threshold=threshold_map
            )
            triggered = float(pred.get(model_name, 0.0))
            buf = oww.prediction_buffer.get(model_name)
            raw_score = float(buf[-1]) if buf else 0.0
            max_score = max(max_score, raw_score)

            now = time.time()
            if now - last_print >= 1.0:
                hit = " <<< WOULD TRIGGER" if triggered > 0 else ""
                if raw_score >= threshold * 0.8:
                    hit = f" (near threshold){hit}"
                print(
                    f"rms={rms:.4f}  raw={raw_score:.3f}  peak={max_score:.3f}{hit}"
                )
                last_print = now

            if triggered > 0:
                print(f"\n*** DETECTED (patience met, raw peak {max_score:.3f}) ***\n")
                oww.reset()
                max_score = 0.0
                time.sleep(1.5)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nDone.")
        sys.exit(0)
