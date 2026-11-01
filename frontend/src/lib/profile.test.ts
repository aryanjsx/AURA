import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { displayName, offerProfilePrompt } from './profile';

let stored: Map<string, string>;

beforeEach(() => {
  stored = new Map();
  vi.stubGlobal('localStorage', {
    getItem: (key: string) => stored.get(key) ?? null,
    setItem: (key: string, value: string) => stored.set(key, value),
  });
});
afterEach(() => vi.unstubAllGlobals());

describe('displayName', () => {
  it('prefers the nickname, then the first name', () => {
    expect(displayName({ first_name: 'Aryan', last_name: 'Kumar', nickname: 'Ary' })).toBe('Ary');
    expect(displayName({ first_name: 'Aryan', last_name: 'Kumar', nickname: '' })).toBe('Aryan');
    expect(displayName({ first_name: '', last_name: 'Kumar', nickname: '' })).toBe('');
    expect(displayName(null)).toBe('');
  });
});

describe('offerProfilePrompt', () => {
  it('waits for setup, then asks exactly once', () => {
    const open = vi.fn();
    offerProfilePrompt({ ready: false, open });
    expect(open).not.toHaveBeenCalled();

    offerProfilePrompt({ ready: true, open });
    offerProfilePrompt({ ready: true, open });
    expect(open).toHaveBeenCalledOnce();
  });
});
