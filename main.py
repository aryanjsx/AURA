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
from aura.core.voice_executor import execute as execute_system_command
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


_VOICE_SYSTEM_PROMPT = "Answer in 1 sentence. Be concise."


def _stream_to_tts(
    ollama: OllamaClient,
    tts: TTSEngine,
    model: str,
    prompt: str,
    system_prompt: str = _VOICE_SYSTEM_PROMPT,
) -> None:
    """Stream LLM tokens and send complete sentences to TTS as they form.

    This gives the user audible feedback within 1-3 seconds of the first
    generated sentence, instead of waiting for the entire response.
    """
    sentence_buf = ""
    full_text = ""
    sent_count = 0
    start = time.perf_counter()

    for token in ollama.chat_stream(
        model=model, prompt=prompt,
        system_prompt=system_prompt, num_predict=200,
    ):
        sentence_buf += token
        full_text += token

        while _has_complete_sentence(sentence_buf):
            sentence, sentence_buf = _split_first_sentence(sentence_buf)
            sentence = sentence.strip()
            if sentence:
                if sent_count == 0:
                    ttfb = int((time.perf_counter() - start) * 1000)
                    print(f"[PIPELINE] First sentence in {ttfb}ms")
                tts.speak(sentence)
                sent_count += 1

    leftover = sentence_buf.strip()
    if leftover:
        tts.speak(leftover)

    total = int((time.perf_counter() - start) * 1000)
    print(f"[PIPELINE] Streamed {len(full_text)} chars in {total}ms ({sent_count + (1 if leftover else 0)} segments)")


def _has_complete_sentence(text: str) -> bool:
    """Check if text contains at least one sentence-ending delimiter."""
    for ch in ".!?\n":
        idx = text.find(ch)
        if idx >= 0 and idx < len(text) - 1:
            return True
    return False


def _split_first_sentence(text: str) -> tuple[str, str]:
    """Split text at the first sentence boundary. Returns (sentence, remainder)."""
    best = len(text)
    for ch in ".!?\n":
        idx = text.find(ch)
        if 0 <= idx < best:
            best = idx
    split_at = best + 1
    return text[:split_at], text[split_at:]


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
        model = intent.model_override or config["models"]["general"]
        print(f"[PIPELINE] Streaming from {model}...")
        _stream_to_tts(ollama, tts, model, intent.cleaned_text)

    elif intent.intent_type == IntentType.SYSTEM_COMMAND:
        result = execute_system_command(intent.cleaned_text)
        if result:
            print(f"[PIPELINE] Executed: {result}")
            tts.speak(result)
        else:
            model = intent.model_override or config["models"]["fast"]
            _stream_to_tts(ollama, tts, model, intent.cleaned_text)

    elif intent.intent_type == IntentType.CODE_GENERATION:
        model = intent.model_override or config["models"]["code"]
        print(f"[PIPELINE] Streaming code response from {model}...")
        _stream_to_tts(
            ollama, tts, model, intent.cleaned_text,
            system_prompt="Summarize the code solution in 1 sentence.",
        )

    elif intent.intent_type == IntentType.DEV_TASK:
        tts.speak(
            f"Dev task recognized: {intent.cleaned_text}. "
            "Execution via safety gate is pending Phase 3 integration."
        )

    elif intent.intent_type == IntentType.VISION_TASK:
        tts.speak("Screen vision is available from Phase 4.")

    elif intent.intent_type == IntentType.REALTIME_QUERY:
        model = intent.model_override or config["models"]["general"]
        _stream_to_tts(ollama, tts, model, intent.cleaned_text)


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

    # 5. Verify models and pre-warm the primary model
    available = ollama.list_models()
    models_cfg = config.get("models", {})
    primary_model = models_cfg.get("general", models_cfg.get("fast", "llama3.2:1b"))
    required = [models_cfg.get("fast"), models_cfg.get("general"), models_cfg.get("code")]
    for m in required:
        if m and m not in available:
            print(f"  [WARN] Model not pulled: {m} — run: ollama pull {m}")
    print(f"[5/8] Model check complete ({len(available)} models available)")
    print(f"[5/8] Pre-warming {primary_model}...")
    ollama.warmup(primary_model)
    print(f"[5/8] {primary_model} ready in RAM")

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

            # Check if the wake transcript already contains a command
            wake_data = payload.data if hasattr(payload, "data") else payload
            wake_command = wake_data.get("command", "").strip() if isinstance(wake_data, dict) else ""

            if wake_command:
                # Command was embedded in the wake phrase (e.g. "Hey Jarvis, what is python?")
                command_text = wake_command
                print(f'[PIPELINE] Command from wake: "{command_text}"')
            else:
                # Keyboard trigger or wake-only phrase — record separately
                print("[PIPELINE] Recording... speak now")
                result = stt.listen_and_transcribe()
                print(
                    f'[PIPELINE] Transcription: "{result.text}" '
                    f"(empty={result.is_empty})"
                )
                if result.is_empty:
                    tts.speak("I didn't catch that. Try again.")
                    print("[PIPELINE] Ready — say 'Hey Jarvis' or press CTRL+SPACE")
                    return
                command_text = result.text

            print("[PIPELINE] Classifying intent...")
            t_classify = time.perf_counter()
            intent = router.classify(command_text)
            classify_ms = int((time.perf_counter() - t_classify) * 1000)
            print(
                f"[PIPELINE] Intent: {intent.intent_type.value} "
                f"(confidence={intent.confidence}, {classify_ms}ms)"
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
