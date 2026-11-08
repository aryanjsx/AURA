import { describe, expect, it } from 'vitest';

import { SpeechSegmenter, matchWakeWord } from './wake-word';

describe('matchWakeWord', () => {
  it.each([
    ['Hey Locus.', ''],
    ['hey locus, set the volume to 30', 'set the volume to 30'],
    ['Locus open my downloads folder.', 'open my downloads folder'],
    ['OK Locus: what time is it?', 'what time is it'],
    ['Hey Lokus', ''],
    ['Hey Lotus, mute', 'mute'],
  ])('wakes on %s', (transcript, command) => {
    expect(matchWakeWord(transcript)).toEqual({ woke: true, command });
  });

  it.each(['', 'Thank you.', 'the locus of control', 'lotus flower', 'focus on this'])(
    'stays asleep for %s',
    (transcript) => {
      expect(matchWakeWord(transcript).woke).toBe(false);
    },
  );
});

describe('SpeechSegmenter', () => {
  function feed(seg: SpeechSegmenter, level: number, from: number, to: number) {
    const events = [];
    for (let t = from; t < to; t += 100) {
      const e = seg.push(level, t);
      if (e) events.push([e, t]);
    }
    return events;
  }

  it('finds a burst of speech', () => {
    const seg = new SpeechSegmenter(700, 3500);
    expect(feed(seg, 0.005, 0, 1000)).toEqual([]);
    expect(feed(seg, 0.2, 1000, 1800)).toEqual([['start', 1000]]);
    expect(feed(seg, 0.005, 1800, 2700)).toEqual([['end', 2400]]);
  });

  it('cuts long speech into pieces', () => {
    const seg = new SpeechSegmenter(700, 1000);
    feed(seg, 0.005, 0, 500);
    expect(feed(seg, 0.2, 500, 1600).map(([e]) => e)).toEqual(['start', 'end']);
  });

  it('ignores steady background noise', () => {
    const seg = new SpeechSegmenter();
    expect(feed(seg, 0.012, 0, 3000)).toEqual([]);
  });
});
