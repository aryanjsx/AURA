import { describe, expect, it } from 'vitest';

import { latestPlan } from './TaskPlan';
import type { ToolCallInfo } from '../../types';

const call = (tool: string, args: unknown, id = Math.random().toString()): ToolCallInfo => ({
  id,
  tool,
  arguments: typeof args === 'string' ? args : JSON.stringify(args),
  status: 'success',
});

describe('latestPlan', () => {
  it('is null without a task_plan call', () => {
    expect(latestPlan(undefined)).toBeNull();
    expect(latestPlan([call('file_read', { path: 'a' })])).toBeNull();
  });

  it('uses the latest plan', () => {
    const plan = latestPlan([
      call('task_plan', { steps: [{ title: 'Find files', status: 'in_progress' }] }),
      call('file_read', { path: 'a' }),
      call('task_plan', {
        steps: [
          { title: 'Find files', status: 'done' },
          { title: 'Move them', status: 'in_progress' },
        ],
      }),
    ]);
    expect(plan).toEqual([
      { title: 'Find files', status: 'done' },
      { title: 'Move them', status: 'in_progress' },
    ]);
  });

  it('skips broken calls and cleans steps', () => {
    const plan = latestPlan([
      call('task_plan', { steps: [{ title: 'Good', status: 'weird' }, { title: '  ' }] }),
      call('task_plan', 'not json'),
    ]);
    expect(plan).toEqual([{ title: 'Good', status: 'pending' }]);
  });
});
