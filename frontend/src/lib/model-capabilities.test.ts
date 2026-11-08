import { describe, expect, it } from 'vitest';

import { isEmbedOnlyModel, isSmallForAgent, modelSizeBillions } from './model-capabilities';

describe('isEmbedOnlyModel', () => {
  it.each([
    'nomic-embed-text',
    'mxbai-embed-large',
    'text-embedding-3-small',
    'all-minilm:latest',
    'hf.co/BAAI/bge-m3:latest',
  ])('classifies %s as embedding-only', (modelId) => {
    expect(isEmbedOnlyModel(modelId)).toBe(true);
  });

  it.each(['qwen3.5:4b', 'codegemma:7b'])('keeps %s available for chat', (modelId) => {
    expect(isEmbedOnlyModel(modelId)).toBe(false);
  });
});

describe('modelSizeBillions', () => {
  it.each([
    ['qwen3.5:4b', 4],
    ['qwen3:0.6b', 0.6],
    ['llama3.1:8b-instruct-q4_K_M', 8],
    ['qwen3.5:35b-a3b', 35],
    ['hf.co/Qwen/Qwen3-1.7B-GGUF', 1.7],
  ])('reads %s as %s billion', (modelId, size) => {
    expect(modelSizeBillions(modelId)).toBe(size);
  });

  it.each(['gpt-4o', 'gemma3n:e4b', 'llama3.1:latest'])('returns null for %s', (modelId) => {
    expect(modelSizeBillions(modelId)).toBeNull();
  });
});

describe('isSmallForAgent', () => {
  it('flags models under 4B', () => {
    expect(isSmallForAgent('qwen3.5:2b')).toBe(true);
    expect(isSmallForAgent('qwen3:0.6b')).toBe(true);
  });

  it('allows 4B and up, and models without a size', () => {
    expect(isSmallForAgent('qwen3.5:4b')).toBe(false);
    expect(isSmallForAgent('qwen3.5:9b')).toBe(false);
    expect(isSmallForAgent('gpt-4o')).toBe(false);
  });
});
