import type { ToolCallInfo } from '../types';
import { describeToolCall } from '../components/Chat/ToolCallCard';

const YES = ['yes', 'yeah', 'yep', 'yup', 'sure', 'ok', 'okay', 'allow', 'go ahead', 'do it', 'approve', 'confirm', 'please do'];
const NO = ['no', 'nope', 'nah', 'deny', "don't", 'do not', 'stop', 'cancel', 'skip', 'never mind', 'nevermind'];

function hasPhrase(text: string, phrases: string[]): boolean {
  return phrases.some((p) => new RegExp(`(^|\\b)${p.replace(/'/g, "'?")}(\\b|$)`).test(text));
}

/** What a spoken answer to an approval means, or null if it's unclear. */
export function parseYesNo(transcript: string): 'yes' | 'no' | null {
  const text = transcript.toLowerCase().replace(/[^a-z' ]+/g, ' ').replace(/\s+/g, ' ').trim();
  if (!text) return null;
  const yes = hasPhrase(text, YES);
  const no = hasPhrase(text, NO);
  if (yes === no) return null; // neither, or both ("yes, no, wait")
  return yes ? 'yes' : 'no';
}

/** Commands and code always need a click; other steps can be answered aloud. */
export function canAnswerByVoice(tc: ToolCallInfo): boolean {
  return tc.risk !== 'run';
}

/** What Locus says when it asks for an approval during a hands-free turn. */
export function approvalQuestion(tc: ToolCallInfo): string {
  const step = describeToolCall(tc.tool, tc.arguments);
  const lowered = step.charAt(0).toLowerCase() + step.slice(1);
  if (!canAnswerByVoice(tc)) {
    return `Locus wants to ${lowered}. That runs a command, so please confirm it on screen.`;
  }
  return `Locus wants to ${lowered}. Should I go ahead? Say yes or no.`;
}
