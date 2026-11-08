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

  it('describes desktop steps in words', () => {
    const d = (tool: string, args: object) => describeToolCall(tool, JSON.stringify(args));
    expect(d('open_path', { path: 'C:/x/report.pdf' })).toBe('Open C:/x/report.pdf');
    expect(d('app_control', { action: 'open', name: 'notepad' })).toBe('Open the app notepad');
    expect(d('app_control', { action: 'close', name: 'chrome' })).toBe('Close chrome');
    expect(d('system_control', { action: 'set_volume', level: 30 })).toBe('Set the volume to 30%');
    expect(d('system_control', { action: 'lock_screen' })).toBe('Lock the screen');
    expect(d('system_control', { action: 'wifi_off' })).toBe('Turn Wi-Fi off');
    expect(d('clipboard', { action: 'read' })).toBe('Read the text on your clipboard');
    expect(d('screenshot', {})).toBe('Take a screenshot of your screen');
  });

  it('falls back to the tool name', () => {
    expect(describeToolCall('git_commit', '{"message":"m"}')).toBe('Commit "m"');
    expect(describeToolCall('new_tool', '{}')).toBe('Use new_tool');
    expect(describeToolCall('shell_exec', 'not json')).toBe('Use shell_exec');
  });
});
