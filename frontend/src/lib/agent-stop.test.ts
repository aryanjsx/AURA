import { describe, expect, it } from 'vitest';

import { stoppedSummary } from './agent-stop';
import type { ToolCallInfo } from '../types';

const tc = (tool: string, args: object, status: ToolCallInfo['status']): ToolCallInfo => ({
  id: tool,
  tool,
  arguments: JSON.stringify(args),
  status,
});

describe('stoppedSummary', () => {
  it('lists the finished steps', () => {
    const text = stoppedSummary(
      [
        tc('task_plan', { steps: [] }, 'success'),
        tc('file_write', { path: 'a.txt', content: 'x' }, 'success'),
        tc('shell_exec', { command: 'dir' }, 'denied'),
        tc('system_control', { action: 'mute' }, 'success'),
      ],
      '',
    );
    expect(text).toBe('Stopped before finishing.\n\nDone so far: Write a.txt; Mute the speakers.');
  });

  it('keeps any partial answer and says when nothing finished', () => {
    expect(stoppedSummary([], 'Working on it')).toBe(
      'Working on it\n\nStopped before finishing.\n\nNo steps were finished.',
    );
  });
});
