import { describe, expect, it } from 'vitest';

import { describeToolCall } from './ToolCallCard';

describe('describeToolCall', () => {
  it('shows the command for shell_exec', () => {
    expect(describeToolCall('shell_exec', JSON.stringify({ command: 'dir' }))).toBe('Run `dir`');
    expect(
      describeToolCall('shell_exec', JSON.stringify({ command: 'ls', working_dir: 'C:/x' })),
    ).toBe('Run `ls` in C:/x');
  });

  it('shows the path for file_write', () => {
    expect(describeToolCall('file_write', JSON.stringify({ path: 'a.txt', content: 'x' }))).toBe(
      'Write a.txt',
    );
    expect(
      describeToolCall('file_write', JSON.stringify({ path: 'a.txt', mode: 'append' })),
    ).toBe('Add to a.txt');
  });

  it('falls back to the tool name', () => {
    expect(describeToolCall('git_commit', '{"message":"m"}')).toBe('Use git_commit');
    expect(describeToolCall('shell_exec', 'not json')).toBe('Use shell_exec');
  });
});
