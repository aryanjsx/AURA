/**
 * Wake word ("Hey Locus") for hands-free voice.
 *
 * There's no separate wake-word model: Locus listens for short bursts of
 * speech, transcribes only those with the local Whisper backend, and checks
 * them for its name. Audio never leaves the computer, which is why this only
 * runs with the `faster-whisper` backend.
 */

/** Speech backends that run on this computer. */
export const LOCAL_SPEECH_BACKENDS = ['faster-whisper'];

// Whisper often hears "Locus" as one of these.
const NAME = '(?:locus|lokus|locas|lockus|low cus)';
const WAKE = new RegExp(`^\\s*(?:(?:hey|hi|okay|ok|hello)[\\s,]+)?${NAME}\\b[\\s,.!?:;-]*(.*)$`, 'i');
// "Hey Lotus" is a common mishearing, but "lotus" alone is a real word.
const WAKE_LOTUS = /^\s*(?:hey|hi|okay|ok)[\s,]+lotus\b[\s,.!?:;-]*(.*)$/i;

/** Whether `transcript` starts with the wake word, and anything said after it. */
export function matchWakeWord(transcript: string): { woke: boolean; command: string } {
  const match = transcript.match(WAKE) ?? transcript.match(WAKE_LOTUS);
  if (!match) return { woke: false, command: '' };
  return { woke: true, command: match[1].trim().replace(/[.!?]+$/, '').trim() };
}

export type SegmentEvent = 'start' | 'end' | null;

/**
 * Finds bursts of speech in the microphone's loudness (RMS every ~100 ms).
 * The noise floor follows quiet moments, so a fan or traffic doesn't count.
 */
export class SpeechSegmenter {
  private floor = 0.01;
  private speaking = false;
  private startedAt = 0;
  private lastLoudAt = 0;

  constructor(
    private readonly silenceMs = 700,
    private readonly maxMs = 3500,
  ) {}

  get threshold(): number {
    return Math.max(this.floor * 3, 0.02);
  }

  push(rms: number, now: number): SegmentEvent {
    const loud = rms >= this.threshold;
    if (!loud) this.floor = this.floor * 0.95 + rms * 0.05;
    if (!this.speaking) {
      if (!loud) return null;
      this.speaking = true;
      this.startedAt = now;
      this.lastLoudAt = now;
      return 'start';
    }
    if (loud) this.lastLoudAt = now;
    if (now - this.lastLoudAt >= this.silenceMs || now - this.startedAt >= this.maxMs) {
      this.speaking = false;
      return 'end';
    }
    return null;
  }
}
