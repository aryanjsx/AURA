/**
 * End-of-speech detection for hands-free voice.
 *
 * Feed it the microphone's loudness (RMS, 0-1) every ~100 ms. It learns the
 * room's noise floor for the first moments, treats anything clearly louder as
 * speech, and reports `done` once the speaker has been quiet for `silenceMs`.
 */

export type VadState = 'waiting' | 'speaking' | 'done' | 'no_speech' | 'too_long';

export interface VadOptions {
  /** Quiet after speech that ends the turn. */
  silenceMs?: number;
  /** Give up if nobody speaks this long. */
  noSpeechMs?: number;
  /** Stop a turn that runs this long. */
  maxMs?: number;
  /** Time spent measuring background noise before listening for speech. */
  calibrateMs?: number;
}

export class SilenceDetector {
  private readonly silenceMs: number;
  private readonly noSpeechMs: number;
  private readonly maxMs: number;
  private readonly calibrateMs: number;
  private startedAt: number | null = null;
  private lastLoudAt: number | null = null;
  private noiseSamples: number[] = [];
  private noiseFloor = 0;
  state: VadState = 'waiting';

  constructor(options: VadOptions = {}) {
    this.silenceMs = options.silenceMs ?? 1200;
    this.noSpeechMs = options.noSpeechMs ?? 8000;
    this.maxMs = options.maxMs ?? 30000;
    this.calibrateMs = options.calibrateMs ?? 300;
  }

  /** Speech must be this loud: well above the noise floor, and audible. */
  get threshold(): number {
    return Math.max(this.noiseFloor * 2.5, 0.02);
  }

  push(rms: number, now: number): VadState {
    if (this.state === 'done' || this.state === 'no_speech' || this.state === 'too_long') {
      return this.state;
    }
    if (this.startedAt === null) this.startedAt = now;
    const elapsed = now - this.startedAt;

    if (elapsed < this.calibrateMs) {
      this.noiseSamples.push(rms);
      this.noiseFloor = this.noiseSamples.reduce((a, b) => a + b, 0) / this.noiseSamples.length;
      return this.state;
    }

    if (rms >= this.threshold) {
      this.lastLoudAt = now;
      this.state = 'speaking';
    }
    if (elapsed >= this.maxMs) {
      this.state = this.state === 'speaking' ? 'too_long' : 'no_speech';
    } else if (this.state === 'speaking' && this.lastLoudAt !== null && now - this.lastLoudAt >= this.silenceMs) {
      this.state = 'done';
    } else if (this.state === 'waiting' && elapsed >= this.noSpeechMs) {
      this.state = 'no_speech';
    }
    return this.state;
  }
}

/** Loudness of one buffer of samples (-1..1), as root mean square. */
export function rms(samples: Float32Array): number {
  if (samples.length === 0) return 0;
  let sum = 0;
  for (let i = 0; i < samples.length; i++) sum += samples[i] * samples[i];
  return Math.sqrt(sum / samples.length);
}

/** The hands-free shortcut: Ctrl+Shift+L, or Cmd+Shift+L on a Mac. */
export const HANDS_FREE_SHORTCUT = 'CommandOrControl+Shift+L';

export function isHandsFreeShortcut(e: { key: string; ctrlKey: boolean; metaKey: boolean; shiftKey: boolean; altKey: boolean }): boolean {
  return e.key.toLowerCase() === 'l' && e.shiftKey && !e.altKey && (e.ctrlKey || e.metaKey);
}
