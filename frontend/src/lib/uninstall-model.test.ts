import { describe, expect, it } from 'vitest';

import { formatBytes } from './api';
import { nextModelAfterUninstall } from './model-capabilities';

describe('nextModelAfterUninstall', () => {
  it('keeps chat on its model when another one is removed', () => {
    expect(nextModelAfterUninstall('qwen3.5:9b', 'qwen3.5:4b', ['qwen3.5:9b'])).toBeNull();
  });

  it('switches chat to a remaining chat model', () => {
    expect(
      nextModelAfterUninstall('qwen3.5:4b', 'qwen3.5:4b', ['nomic-embed-text', 'qwen3.5:9b']),
    ).toBe('qwen3.5:9b');
  });

  it('says when no chat model is left', () => {
    expect(nextModelAfterUninstall('qwen3.5:4b', 'qwen3.5:4b', ['nomic-embed-text'])).toBe('');
  });
});

describe('formatBytes', () => {
  it('shows GB and MB', () => {
    expect(formatBytes(6_600_000_000)).toBe('6.6 GB');
    expect(formatBytes(274_000_000)).toBe('274 MB');
    expect(formatBytes(512)).toBe('512 bytes');
  });
});
