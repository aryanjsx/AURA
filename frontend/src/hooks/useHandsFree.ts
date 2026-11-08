import { useCallback, useEffect, useRef } from 'react';
import { toast } from 'sonner';
import { isTauri } from '../lib/api';
import { useAppStore } from '../lib/store';
import { useTtsStore } from '../lib/tts';
import { HANDS_FREE_SHORTCUT, isHandsFreeShortcut, type VadState } from '../lib/vad';
import type { RecordingOptions, SpeechState } from './useSpeech';

interface Options {
  enabled: boolean;
  /** Speech recognition is set up on the server. */
  available: boolean;
  state: SpeechState;
  startRecording: (options?: RecordingOptions) => Promise<void>;
  stopRecording: () => Promise<string>;
  cancelRecording: () => void;
  /** Sends the transcript as a chat message. */
  send: (text: string) => void;
}

/**
 * Hands-free voice: Ctrl/Cmd+Shift+L (in the window, and system-wide in the
 * desktop app) stops any spoken reply, listens until the user stops talking,
 * sends what they said and has the reply read aloud. Pressing it again while
 * listening sends straight away.
 */
export function useHandsFree({
  enabled,
  available,
  state,
  startRecording,
  stopRecording,
  cancelRecording,
  send,
}: Options) {
  const finish = useCallback(
    async (reason: VadState) => {
      if (reason === 'no_speech') {
        cancelRecording();
        toast("Didn't hear anything. Press Ctrl+Shift+L to try again.");
        return;
      }
      try {
        const text = (await stopRecording()).trim();
        if (!text) return;
        useAppStore.getState().setSpeakNextReply(true);
        send(text);
      } catch {
        // useSpeech reports transcription errors.
      }
    },
    [cancelRecording, stopRecording, send],
  );

  const listen = useCallback(async () => {
    if (!available) {
      toast.error('Speech recognition isn’t set up. Turn it on under Settings > Speech.');
      return;
    }
    useTtsStore.getState().stop(); // talking over a reply interrupts it
    if (state === 'recording') {
      void finish('done');
      return;
    }
    if (state === 'transcribing') return;
    await startRecording({ onEndOfSpeech: (reason) => void finish(reason) });
  }, [available, state, startRecording, finish]);

  // The global shortcut outlives renders, so it calls the latest `listen`.
  const listenRef = useRef(listen);
  useEffect(() => {
    listenRef.current = listen;
  }, [listen]);

  useEffect(() => {
    if (!enabled) return;
    const onKey = (e: KeyboardEvent) => {
      if (!isHandsFreeShortcut(e)) return;
      e.preventDefault();
      void listenRef.current();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [enabled]);

  useEffect(() => {
    if (!enabled || !isTauri()) return;
    let registered = false;
    let cancelled = false;
    (async () => {
      try {
        const { register } = await import('@tauri-apps/plugin-global-shortcut');
        await register(HANDS_FREE_SHORTCUT, async (event) => {
          if (event.state !== 'Pressed') return;
          try {
            const { getCurrentWindow } = await import('@tauri-apps/api/window');
            const win = getCurrentWindow();
            await win.unminimize();
            await win.show();
            await win.setFocus();
          } catch {
            // Listening still works if the window can't be raised.
          }
          void listenRef.current();
        });
        registered = true;
        if (cancelled) {
          const { unregister } = await import('@tauri-apps/plugin-global-shortcut');
          await unregister(HANDS_FREE_SHORTCUT);
        }
      } catch (err) {
        console.warn('Hands-free shortcut unavailable:', err);
      }
    })();
    return () => {
      cancelled = true;
      if (!registered) return;
      void import('@tauri-apps/plugin-global-shortcut')
        .then(({ unregister }) => unregister(HANDS_FREE_SHORTCUT))
        .catch(() => {});
    };
  }, [enabled]);

  return { listen };
}
