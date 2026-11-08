import { describe, expect, it } from 'vitest';

import { shouldSuggestAgentModel } from './model-capabilities';

describe('shouldSuggestAgentModel', () => {
  it('suggests a bigger model over small ones', () => {
    expect(shouldSuggestAgentModel('qwen3.5:4b', 'qwen3.5:9b')).toBe(true);
    expect(shouldSuggestAgentModel('qwen3:0.6b', 'qwen3.5:9b')).toBe(true);
  });

  it('leaves good, unknown and matching models alone', () => {
    expect(shouldSuggestAgentModel('qwen3.5:9b', 'qwen3.5:9b')).toBe(false);
    expect(shouldSuggestAgentModel('llama3.1:8b', 'qwen3.5:9b')).toBe(false);
    expect(shouldSuggestAgentModel('gpt-4o', 'qwen3.5:9b')).toBe(false);
    expect(shouldSuggestAgentModel('qwen3.5:4b', '')).toBe(false);
  });
});
