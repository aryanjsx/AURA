import { describe, expect, it } from 'vitest';

import { SilenceDetector, isHandsFreeShortcut, rms } from './vad';

/** Feed `level` every 100 ms from `from` to `to` (ms). */
function feed(vad: SilenceDetector, level: number, from: number, to: number) {
  let state = vad.state;
  for (let t = from; t < to; t += 100) state = vad.push(level, t);
  return state;
}

describe('SilenceDetector', () => {
  it('ends the turn after speech and then quiet', () => {
    const vad = new SilenceDetector({ silenceMs: 1000 });
    feed(vad, 0.005, 0, 300); // room noise
    expect(feed(vad, 0.2, 300, 2000)).toBe('speaking');
    expect(feed(vad, 0.006, 2000, 2800)).toBe('speaking');
    expect(feed(vad, 0.006, 2800, 3200)).toBe('done');
  });

  it('keeps listening through short pauses', () => {
    const vad = new SilenceDetector({ silenceMs: 1000 });
    feed(vad, 0.005, 0, 300);
    feed(vad, 0.2, 300, 1000);
    feed(vad, 0.005, 1000, 1500); // half a second's pause
    expect(feed(vad, 0.2, 1500, 2000)).toBe('speaking');
  });

  it('gives up when nobody speaks', () => {
    const vad = new SilenceDetector({ noSpeechMs: 2000 });
    expect(feed(vad, 0.004, 0, 2100)).toBe('no_speech');
  });

  it('adapts to a noisy room', () => {
    const vad = new SilenceDetector({ noSpeechMs: 2000 });
    feed(vad, 0.05, 0, 300); // loud background
    expect(vad.threshold).toBeCloseTo(0.125);
    expect(feed(vad, 0.06, 300, 2100)).toBe('no_speech');
  });

  it('stops a turn that runs too long', () => {
    const vad = new SilenceDetector({ maxMs: 1000 });
    feed(vad, 0.004, 0, 300);
    expect(feed(vad, 0.3, 300, 1100)).toBe('too_long');
  });
});

describe('rms', () => {
  it('measures loudness', () => {
    expect(rms(new Float32Array([]))).toBe(0);
    expect(rms(new Float32Array([0.5, -0.5, 0.5, -0.5]))).toBeCloseTo(0.5);
  });
});

describe('isHandsFreeShortcut', () => {
  const key = (over: object) => ({ key: 'L', ctrlKey: false, metaKey: false, shiftKey: true, altKey: false, ...over });
  it('matches Ctrl+Shift+L and Cmd+Shift+L only', () => {
    expect(isHandsFreeShortcut(key({ ctrlKey: true }))).toBe(true);
    expect(isHandsFreeShortcut(key({ metaKey: true }))).toBe(true);
    expect(isHandsFreeShortcut(key({}))).toBe(false);
    expect(isHandsFreeShortcut(key({ ctrlKey: true, altKey: true }))).toBe(false);
    expect(isHandsFreeShortcut(key({ ctrlKey: true, key: 'k' }))).toBe(false);
  });
});
