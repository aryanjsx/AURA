import { describe, expect, it } from 'vitest';

import { approvalQuestion, canAnswerByVoice, parseYesNo } from './voice-approval';
import type { ToolCallInfo } from '../types';

const tc = (tool: string, args: object, risk: 'change' | 'run'): ToolCallInfo => ({
  id: 'x',
  tool,
  arguments: JSON.stringify(args),
  status: 'awaiting_approval',
  risk,
});

describe('parseYesNo', () => {
  it.each(['Yes', 'yeah sure', 'Okay, go ahead.', 'allow it', 'Yes please do'])('hears yes in %s', (t) => {
    expect(parseYesNo(t)).toBe('yes');
  });

  it.each(['No', 'nope', "Don't do that", 'cancel', 'stop', 'never mind'])('hears no in %s', (t) => {
    expect(parseYesNo(t)).toBe('no');
  });

  it.each(['', 'hmm', 'what was that', 'yes no wait', 'nobody knows'])('is unsure about %s', (t) => {
    expect(parseYesNo(t)).toBeNull();
  });
});

describe('approvals by voice', () => {
  it('asks aloud for change-level steps only', () => {
    const volume = tc('system_control', { action: 'set_volume', level: 30 }, 'change');
    const shell = tc('shell_exec', { command: 'dir' }, 'run');

    expect(canAnswerByVoice(volume)).toBe(true);
    expect(canAnswerByVoice(shell)).toBe(false);
    expect(approvalQuestion(volume)).toBe(
      'Locus wants to set the volume to 30%. Should I go ahead? Say yes or no.',
    );
    expect(approvalQuestion(shell)).toContain('please confirm it on screen');
  });
});
