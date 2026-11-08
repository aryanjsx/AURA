import { useEffect, useRef } from 'react';
import { toast } from 'sonner';
import { fetchSpeechHealth, transcribeAudio } from '../lib/api';
import { rms } from '../lib/vad';
import { LOCAL_SPEECH_BACKENDS, SpeechSegmenter, matchWakeWord } from '../lib/wake-word';

/** Bursts shorter than this are clicks or coughs, not words. */
const MIN_SEGMENT_MS = 300;

interface Options {
  enabled: boolean;
  /** Locus is listening, answering or speaking: ignore the microphone. */
  busy: boolean;
  /** "Hey Locus" was heard; `command` is anything said after it. */
  onWake: (command: string) => void;
}

/**
 * Listens for "Hey Locus" while enabled. The microphone stays on, but only
 * short bursts of speech are transcribed, by the local Whisper backend.
 */
export function useWakeWord({ enabled, busy, onWake }: Options) {
  const busyRef = useRef(busy);
  const onWakeRef = useRef(onWake);
  useEffect(() => {
    busyRef.current = busy;
    onWakeRef.current = onWake;
  }, [busy, onWake]);

  useEffect(() => {
    if (!enabled) return;
    let stopped = false;
    let stream: MediaStream | null = null;
    let context: AudioContext | null = null;
    let timer: number | null = null;

    (async () => {
      const health = await fetchSpeechHealth().catch(() => null);
      if (!health?.available || !LOCAL_SPEECH_BACKENDS.includes(health.backend ?? '')) {
        toast.error('"Hey Locus" needs the local Whisper speech backend (faster-whisper), so audio stays on this computer.');
        return;
      }
      if (stopped || !navigator.mediaDevices?.getUserMedia || typeof AudioContext === 'undefined') return;
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      } catch {
        toast.error('"Hey Locus" needs microphone access.');
        return;
      }
      if (stopped) {
        stream.getTracks().forEach((t) => t.stop());
        return;
      }
      context = new AudioContext();
      const analyser = context.createAnalyser();
      analyser.fftSize = 2048;
      context.createMediaStreamSource(stream).connect(analyser);
      const samples = new Float32Array(analyser.fftSize);
      const segmenter = new SpeechSegmenter();
      let recorder: MediaRecorder | null = null;
      let chunks: Blob[] = [];
      let startedAt = 0;

      const finish = (rec: MediaRecorder, duration: number) => {
        rec.onstop = async () => {
          const blob = new Blob(chunks, { type: rec.mimeType || 'audio/webm' });
          chunks = [];
          if (stopped || duration < MIN_SEGMENT_MS || busyRef.current) return;
          try {
            const { text } = await transcribeAudio(blob);
            const { woke, command } = matchWakeWord(text || '');
            if (woke && !busyRef.current && !stopped) onWakeRef.current(command);
          } catch {
            // A failed transcription just means no wake word this time.
          }
        };
        rec.stop();
      };

      timer = window.setInterval(() => {
        if (!stream) return;
        if (busyRef.current) {
          if (recorder?.state === 'recording') {
            recorder.onstop = null;
            recorder.stop();
          }
          recorder = null;
          return;
        }
        analyser.getFloatTimeDomainData(samples);
        const event = segmenter.push(rms(samples), performance.now());
        if (event === 'start') {
          chunks = [];
          recorder = new MediaRecorder(stream);
          recorder.ondataavailable = (e) => {
            if (e.data.size > 0) chunks.push(e.data);
          };
          recorder.start();
          startedAt = performance.now();
        } else if (event === 'end' && recorder?.state === 'recording') {
          finish(recorder, performance.now() - startedAt);
          recorder = null;
        }
      }, 100);
    })();

    return () => {
      stopped = true;
      if (timer !== null) window.clearInterval(timer);
      stream?.getTracks().forEach((t) => t.stop());
      void context?.close().catch(() => {});
    };
  }, [enabled]);
}
