import { useState, useCallback, useRef, useEffect } from 'react';
import { transcribeAudio, fetchSpeechHealth } from '../lib/api';
import { SilenceDetector, rms, type VadState } from '../lib/vad';

export type SpeechState = 'idle' | 'recording' | 'transcribing';

export interface RecordingOptions {
  /**
   * Hands-free: called once when the speaker stops talking (`done`), nobody
   * spoke (`no_speech`) or the turn ran too long (`too_long`).
   */
  onEndOfSpeech?: (reason: VadState) => void;
}

export function useSpeech() {
  const [state, setState] = useState<SpeechState>('idle');
  const [error, setError] = useState<string | null>(null);
  const [available, setAvailable] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  // End-of-speech detection, while a hands-free recording runs.
  const vadRef = useRef<{ context: AudioContext; timer: number } | null>(null);

  // Check if speech backend is available on mount
  useEffect(() => {
    fetchSpeechHealth()
      .then((health) => setAvailable(health.available))
      .catch(() => setAvailable(false));
  }, []);

  const stopListening = useCallback(() => {
    const vad = vadRef.current;
    if (vad) {
      window.clearInterval(vad.timer);
      void vad.context.close().catch(() => {});
      vadRef.current = null;
    }
  }, []);

  const releaseMic = useCallback(() => {
    stopListening();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }, [stopListening]);

  useEffect(() => releaseMic, [releaseMic]);

  const startRecording = useCallback(async (options: RecordingOptions = {}): Promise<void> => {
    setError(null);

    if (!navigator.mediaDevices?.getUserMedia) {
      setError('Microphone not supported in this browser');
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.start();
      mediaRecorderRef.current = recorder;
      setState('recording');

      if (options.onEndOfSpeech && typeof AudioContext !== 'undefined') {
        const context = new AudioContext();
        const analyser = context.createAnalyser();
        analyser.fftSize = 2048;
        context.createMediaStreamSource(stream).connect(analyser);
        const samples = new Float32Array(analyser.fftSize);
        const detector = new SilenceDetector();
        const onEnd = options.onEndOfSpeech;
        const timer = window.setInterval(() => {
          analyser.getFloatTimeDomainData(samples);
          const result = detector.push(rms(samples), performance.now());
          if (result === 'done' || result === 'no_speech' || result === 'too_long') {
            stopListening();
            onEnd(result);
          }
        }, 100);
        vadRef.current = { context, timer };
      }
    } catch (err) {
      setError('Microphone access denied');
      setState('idle');
    }
  }, [stopListening]);

  const stopRecording = useCallback(async (): Promise<string> => {
    return new Promise((resolve, reject) => {
      const recorder = mediaRecorderRef.current;
      if (!recorder || recorder.state !== 'recording') {
        reject(new Error('Not recording'));
        return;
      }

      recorder.onstop = async () => {
        setState('transcribing');

        // Stop all audio tracks
        releaseMic();

        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' });
        chunksRef.current = [];

        try {
          const result = await transcribeAudio(blob);
          setState('idle');
          resolve(result.text);
        } catch (err) {
          setState('idle');
          const msg = err instanceof Error ? err.message : 'Transcription failed';
          setError(msg);
          reject(err);
        }
      };

      recorder.stop();
    });
  }, [releaseMic]);

  /** Stop recording and throw the audio away (nobody spoke, or Esc). */
  const cancelRecording = useCallback(() => {
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state === 'recording') {
      recorder.onstop = null;
      recorder.stop();
    }
    chunksRef.current = [];
    releaseMic();
    setState('idle');
  }, [releaseMic]);

  return {
    state,
    error,
    available,
    startRecording,
    stopRecording,
    cancelRecording,
    isRecording: state === 'recording',
    isTranscribing: state === 'transcribing',
  };
}
