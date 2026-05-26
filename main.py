"""
AURA — Phase 2 Voice Pipeline Entry Point.

Ties all pipeline layers together: wake word → STT → intent router →
LLM/executor → TTS. This is the primary entry point for voice mode.

The Phase 1 CLI entry (aura/cli.py) remains available via `python -m aura`.
This file starts the full voice pipeline via `python main.py`.
"""

from __future__ import annotations

import logging
import sys
import time

from aura.core.config_loader import load_config
from aura.core.intent_router import IntentObject, IntentRouter, IntentType
from aura.core.ollama_client import OllamaClient
from aura.modules.stt import STTEngine
from aura.modules.tts import TTSEngine
from aura.modules.wake_word import WakeWordListener
from aura.utils.event_bus import EventType, bus
from aura.utils.mode_monitor import mode_monitor

BANNER = r"""
    ___   __  ______  ___
   /   | / / / / __ \/   |
  / /| |/ / / / /_/ / /| |
 / ___ / /_/ / _, _/ ___ |
/_/  |_\____/_/ |_/_/  |_|

 Phase 2 — Voice Pipeline Active
"""


def _dispatch(
    intent: IntentObject,
    tts: TTSEngine,
    ollama: OllamaClient,
    config: dict,
) -> None:
    """Route a classified IntentObject to the appropriate handler."""

    if intent.intent_type in (
        IntentType.GENERAL_KNOWLEDGE,
        IntentType.PROJECT_CONTEXT,
        IntentType.UNKNOWN,
    ):
        print("[PIPELINE] Waiting for Ollama response...")
        response = ollama.chat(
            model=intent.model_override or config["models"]["general"],
            prompt=intent.cleaned_text,
            system_prompt=(
                "You are AURA, a voice assistant. Reply in 1-2 sentences maximum. "
                "Be direct and concise — your answer will be spoken aloud."
            ),
        )
        print(f"[PIPELINE] LLM replied ({len(response.text)} chars, {response.duration_ms}ms)")
        print(f"[PIPELINE] Speaking: {response.text[:100]}...")
        tts.speak(response.text)

    elif intent.intent_type == IntentType.SYSTEM_COMMAND:
        tts.speak(
            f"System command recognized: {intent.cleaned_text}. "
            "Execution via safety gate is pending Phase 3 integration."
        )

    elif intent.intent_type == IntentType.CODE_GENERATION:
        response = ollama.chat(
            model=intent.model_override or config["models"]["code"],
            prompt=intent.cleaned_text,
        )
        tts.speak("Code generated. Opening in editor.")

    elif intent.intent_type == IntentType.DEV_TASK:
        tts.speak(
            f"Dev task recognized: {intent.cleaned_text}. "
            "Execution via safety gate is pending Phase 3 integration."
        )

    elif intent.intent_type == IntentType.VISION_TASK:
        tts.speak("Screen vision is available from Phase 4.")

    elif intent.intent_type == IntentType.REALTIME_QUERY:
        routing_cfg = config.get("routing", {})
        if routing_cfg.get("realtime_warning", True):
            tts.speak("Note: my knowledge may be outdated for this query.")
        response = ollama.chat(
            model=intent.model_override or config["models"]["general"],
            prompt=intent.cleaned_text,
        )
        tts.speak(response.text)


def startup() -> None:
    """Full Phase 2 pipeline startup sequence."""
    print(BANNER)

    # 1. Load and validate config
    config = load_config()
    print("[1/8] Configuration loaded and validated")

    # 2. Start connectivity monitor
    mode_monitor.start()
    print(f"[2/8] Mode monitor started — {mode_monitor.current_mode}")

    # 3. Pre-load Whisper model
    stt = STTEngine(config)
    print("[3/8] Loading Whisper model (this may take a moment)...")
    stt.preload()
    print("[3/8] Whisper model ready")

    # 4. Ollama health check
    ollama = OllamaClient(config)
    if not ollama.health_check():
        print("\n[ERROR] Ollama not running. Start with: ollama serve")
        sys.exit(1)
    print("[4/8] Ollama reachable")

    # 5. Verify models are pulled
    available = ollama.list_models()
    models_cfg = config.get("models", {})
    required = [models_cfg.get("fast"), models_cfg.get("general"), models_cfg.get("code")]
    for m in required:
        if m and m not in available:
            print(f"  [WARN] Model not pulled: {m} — run: ollama pull {m}")
    print(f"[5/8] Model check complete ({len(available)} models available)")

    # 6. Build pipeline components
    router = IntentRouter(config, ollama)
    tts = TTSEngine(config)
    wake = WakeWordListener(config)
    wake.set_whisper_model(stt._model)
    tts.start()
    print("[6/8] Pipeline components built")

    # 7. Wire the pipeline via event bus
    def on_wake(payload) -> None:
        print("\n[PIPELINE] Wake triggered!")
        wake.pause()
        try:
            tts.interrupt()
            print("[PIPELINE] Recording... speak now")
            result = stt.listen_and_transcribe()
            print(
                f"[PIPELINE] Transcription: \"{result.text}\" "
                f"(empty={result.is_empty})"
            )
            if result.is_empty:
                tts.speak("I didn't catch that. Try again.")
                print("[PIPELINE] Ready — say 'Hey Jarvis' or press CTRL+SPACE")
                return
            print("[PIPELINE] Classifying intent...")
            intent = router.classify(result.text)
            print(
                f"[PIPELINE] Intent: {intent.intent_type.value} "
                f"(confidence={intent.confidence})"
            )
            print(f"[PIPELINE] Dispatching to model: {intent.model_override}")
            _dispatch(intent, tts, ollama, config)
            print("[PIPELINE] Ready — say 'Hey Jarvis' or press CTRL+SPACE")
        finally:
            tts.wait_until_idle()
            wake.resume()

    bus.subscribe(EventType.WAKE_WORD_DETECTED, on_wake)
    print("[7/8] Event pipeline wired")

    # 8. Start wake word listener (after startup TTS so speakers don't block detection)
    wake.start()
    logger = logging.getLogger("aura.main")
    logger.info(
        "[AURA] Wake word: Tier 1=Whisper (hey jarvis) | "
        "Tier 2=openwakeword | Tier 3=CTRL+SPACE"
    )
    wake.pause()
    tts.speak("AURA online. Say Hey Jarvis or press Control Space to activate.")
    tts.wait_until_idle()
    wake.resume()
    print("[8/8] Wake word listener active")
    print("\n" + "=" * 50)
    print("AURA Phase 2 Pipeline running.")
    print("Say 'Hey Jarvis' or press CTRL+SPACE to activate.")
    print("Press CTRL+C to shut down.")
    print("=" * 50)

    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\nShutting down AURA...")
        wake.stop()
        mode_monitor.stop()
        print("Goodbye.")


if __name__ == "__main__":
    startup()
