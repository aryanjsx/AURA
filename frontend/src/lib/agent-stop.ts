import type { ToolCallInfo } from '../types';
import { describeToolCall } from '../components/Chat/ToolCallCard';

/** Sent by Continue on a stopped Agent mode task. */
export const CONTINUE_PROMPT =
  "Continue the task from where you stopped. Don't redo the steps you already finished.";

/**
 * The reply for an Agent mode task the user stopped. It stays in the
 * conversation, so a later Continue tells the agent what was already done.
 */
export function stoppedSummary(toolCalls: ToolCallInfo[], partial: string): string {
  const finished = toolCalls
    .filter((tc) => tc.tool !== 'task_plan' && tc.status === 'success')
    .map((tc) => describeToolCall(tc.tool, tc.arguments));
  const lines = [partial.trim(), 'Stopped before finishing.'].filter(Boolean);
  lines.push(
    finished.length > 0
      ? `Done so far: ${finished.join('; ')}.`
      : 'No steps were finished.',
  );
  return lines.join('\n\n');
}
