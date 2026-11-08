import { useState } from 'react';
import { ChevronDown, ChevronRight, Loader2, CheckCircle2, XCircle, ShieldQuestion, Ban, Undo2 } from 'lucide-react';
import { toast } from 'sonner';
import type { ToolCallInfo } from '../../types';
import { serializeToolCallArguments } from '../../lib/tool-call';
import { answerApproval, undoChange, type ApprovalDecision } from '../../lib/api';

interface Props {
  toolCall: ToolCallInfo;
}

const statusConfig = {
  running: { icon: Loader2, color: 'var(--color-accent)' },
  success: { icon: CheckCircle2, color: 'var(--color-success)' },
  error: { icon: XCircle, color: 'var(--color-error)' },
  awaiting_approval: { icon: ShieldQuestion, color: 'var(--color-warning, var(--color-accent))' },
  approved: { icon: Loader2, color: 'var(--color-accent)' },
  denied: { icon: Ban, color: 'var(--color-text-tertiary)' },
};

/** What the agent wants to do, in words, for the approval prompt. */
export function describeToolCall(tool: string, argumentsText: string): string {
  let args: Record<string, unknown> = {};
  try {
    const parsed = JSON.parse(argumentsText);
    if (parsed && typeof parsed === 'object') args = parsed;
  } catch {
    /* fall through */
  }
  const text = (key: string) => (typeof args[key] === 'string' ? (args[key] as string) : '');
  if (tool === 'shell_exec' && text('command')) {
    const where = text('working_dir');
    return where ? `Run \`${text('command')}\` in ${where}` : `Run \`${text('command')}\``;
  }
  if (tool === 'file_write' && text('path')) {
    return text('mode') === 'append' ? `Add to ${text('path')}` : `Write ${text('path')}`;
  }
  const action = text('action');
  const level = typeof args.level === 'number' ? `${args.level}%` : '';
  if (tool === 'open_path' && text('path')) return `Open ${text('path')}`;
  if (tool === 'app_control' && text('name')) {
    if (action === 'open') return `Open the app ${text('name')}`;
    if (action === 'close') return `Close ${text('name')}`;
  }
  if (tool === 'system_control') {
    const settings: Record<string, string> = {
      set_volume: `Set the volume to ${level}`,
      mute: 'Mute the speakers',
      unmute: 'Unmute the speakers',
      set_brightness: `Set the screen brightness to ${level}`,
      dark_mode: 'Switch to dark mode',
      light_mode: 'Switch to light mode',
      lock_screen: 'Lock the screen',
      wifi_on: 'Turn Wi-Fi on',
      wifi_off: 'Turn Wi-Fi off',
      bluetooth_on: 'Turn Bluetooth on',
      bluetooth_off: 'Turn Bluetooth off',
    };
    if (settings[action]) return settings[action];
  }
  if (tool === 'clipboard') {
    if (action === 'read') return 'Read the text on your clipboard';
    if (action === 'write') return 'Copy text to your clipboard';
  }
  if (tool === 'screenshot') return 'Take a screenshot of your screen';
  if (tool === 'git_commit' && text('message')) return `Commit "${text('message')}"`;
  return `Use ${tool}`;
}

function lowerFirst(text: string): string {
  return text.charAt(0).toLowerCase() + text.slice(1);
}

function ApprovalPrompt({ toolCall, argumentsText }: { toolCall: ToolCallInfo; argumentsText: string }) {
  const [sending, setSending] = useState(false);
  const answer = async (decision: ApprovalDecision) => {
    if (!toolCall.approvalId) return;
    setSending(true);
    try {
      const waiting = await answerApproval(toolCall.approvalId, decision);
      if (!waiting) toast.error('This request is no longer waiting for an answer.');
    } catch (err: any) {
      toast.error(err?.message || 'Could not send your answer.');
    } finally {
      setSending(false);
    }
  };
  const button = (label: string, decision: ApprovalDecision, primary = false) => (
    <button
      type="button"
      disabled={sending}
      onClick={() => answer(decision)}
      className="px-2.5 py-1 rounded-md text-xs cursor-pointer disabled:cursor-default disabled:opacity-50"
      style={{
        background: primary ? 'var(--color-accent)' : 'transparent',
        color: primary ? 'var(--color-on-accent, #fff)' : 'var(--color-text-secondary)',
        border: `1px solid ${primary ? 'var(--color-accent)' : 'var(--color-border)'}`,
        fontFamily: 'inherit',
      }}
    >
      {label}
    </button>
  );
  return (
    <div
      className="px-2.5 py-2 flex flex-col gap-2"
      style={{
        borderTop: '1px solid var(--color-border-subtle, var(--color-border))',
        fontFamily: 'var(--font-sans, inherit)',
      }}
    >
      <div style={{ color: 'var(--color-text)', fontSize: 12 }}>
        Allow Locus to{' '}
        <span style={{ fontWeight: 500 }}>{lowerFirst(describeToolCall(toolCall.tool, argumentsText))}</span>?
      </div>
      {toolCall.preview && (
        <pre
          className="p-1.5 rounded overflow-auto"
          style={{
            background: 'var(--color-code-bg, rgba(0,0,0,0.2))',
            color: 'var(--color-text-secondary)',
            fontSize: 11,
            lineHeight: 1.4,
            maxHeight: 220,
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
            fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
          }}
        >
          {toolCall.preview}
        </pre>
      )}
      <div className="flex flex-wrap gap-1.5">
        {button('Allow', 'approve', true)}
        {button(`Allow ${toolCall.tool} for this task`, 'approve_tool')}
        {toolCall.canAlways && button('Always allow', 'always')}
        {button('Deny', 'deny')}
      </div>
    </div>
  );
}

function previewArgs(raw: string): string {
  if (!raw) return '';
  try {
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === 'object') {
      const entries = Object.entries(parsed);
      if (entries.length === 0) return '';
      const [k, v] = entries[0];
      const valStr =
        typeof v === 'string' ? v : JSON.stringify(v);
      const trimmed = valStr.length > 40 ? `${valStr.slice(0, 40)}…` : valStr;
      return entries.length === 1 ? `${k}: ${trimmed}` : `${k}: ${trimmed}, …`;
    }
  } catch {
    /* fall through */
  }
  return raw.length > 60 ? `${raw.slice(0, 60)}…` : raw;
}

function UndoButton({ toolCall }: { toolCall: ToolCallInfo }) {
  const [state, setState] = useState<'ready' | 'working' | 'done'>(toolCall.undone ? 'done' : 'ready');
  if (state === 'done') {
    return <span style={{ color: 'var(--color-text-tertiary)', fontSize: 10, flexShrink: 0 }}>Undone</span>;
  }
  const undo = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!toolCall.undoId) return;
    setState('working');
    try {
      const { ok, message } = await undoChange(toolCall.undoId);
      if (ok) {
        toolCall.undone = true;
        setState('done');
        toast.success(message);
      } else {
        setState('ready');
        toast.error(message);
      }
    } catch (err: any) {
      setState('ready');
      toast.error(err?.message || 'Could not undo the change.');
    }
  };
  return (
    <span
      role="button"
      tabIndex={0}
      onClick={undo}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') undo(e as any);
      }}
      aria-disabled={state === 'working'}
      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded cursor-pointer"
      style={{
        color: 'var(--color-text-secondary)',
        border: '1px solid var(--color-border)',
        fontSize: 10,
        flexShrink: 0,
        opacity: state === 'working' ? 0.5 : 1,
      }}
      title="Put the file back the way it was"
    >
      <Undo2 size={10} />
      Undo
    </span>
  );
}

export function ToolCallCard({ toolCall }: Props) {
  const [expanded, setExpanded] = useState(false);
  const config = statusConfig[toolCall.status] ?? statusConfig.running;
  const StatusIcon = config.icon;
  // Persisted conversations may contain the pre-fix object payload despite
  // the TypeScript contract, so normalize again at the final render boundary.
  const argumentsText = serializeToolCallArguments(toolCall.arguments);
  const preview = previewArgs(argumentsText);

  return (
    <div
      className="rounded-md text-xs overflow-hidden"
      style={{
        border: '1px solid var(--color-border-subtle, var(--color-border))',
        background: 'var(--color-bg-tertiary, var(--color-bg-secondary))',
        fontFamily:
          'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace',
      }}
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 w-full px-2.5 py-1.5 cursor-pointer text-left"
        style={{ background: 'transparent' }}
      >
        {expanded ? (
          <ChevronDown size={11} style={{ color: 'var(--color-text-tertiary)', flexShrink: 0 }} />
        ) : (
          <ChevronRight size={11} style={{ color: 'var(--color-text-tertiary)', flexShrink: 0 }} />
        )}
        <StatusIcon
          size={11}
          style={{ color: config.color, flexShrink: 0 }}
          className={toolCall.status === 'running' || toolCall.status === 'approved' ? 'animate-spin' : ''}
        />
        <span
          style={{ color: 'var(--color-text)', fontWeight: 500, flexShrink: 0 }}
        >
          {toolCall.tool}
        </span>
        {preview && !expanded && (
          <span
            className="truncate"
            style={{ color: 'var(--color-text-tertiary)', fontSize: 10.5 }}
          >
            {preview}
          </span>
        )}
        <div className="flex-1" />
        {toolCall.status === 'success' && toolCall.undoId && <UndoButton toolCall={toolCall} />}
        {toolCall.status === 'denied' && (
          <span style={{ color: 'var(--color-text-tertiary)', fontSize: 10, flexShrink: 0 }}>
            Denied
          </span>
        )}
        {toolCall.latency != null && (
          <span
            style={{
              color: 'var(--color-text-tertiary)',
              fontSize: 10,
              flexShrink: 0,
            }}
          >
            {toolCall.latency < 1000
              ? `${Math.round(toolCall.latency)}ms`
              : `${(toolCall.latency / 1000).toFixed(1)}s`}
          </span>
        )}
      </button>
      {toolCall.status === 'awaiting_approval' && toolCall.approvalId && (
        <ApprovalPrompt toolCall={toolCall} argumentsText={argumentsText} />
      )}
      {expanded && (
        <div
          className="px-2.5 pb-2 pt-0.5"
          style={{ borderTop: '1px solid var(--color-border-subtle, var(--color-border))' }}
        >
          {argumentsText && (
            <div className="mt-1.5">
              <div
                style={{
                  color: 'var(--color-text-tertiary)',
                  fontSize: 9.5,
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  marginBottom: 3,
                }}
              >
                args
              </div>
              <pre
                className="p-1.5 rounded overflow-auto"
                style={{
                  background: 'var(--color-code-bg, rgba(0,0,0,0.2))',
                  color: 'var(--color-text-secondary)',
                  fontSize: 11,
                  lineHeight: 1.4,
                  maxHeight: 120,
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-all',
                }}
              >
                {formatJson(argumentsText)}
              </pre>
            </div>
          )}
          {toolCall.result && (
            <div className="mt-1.5">
              <div
                style={{
                  color: 'var(--color-text-tertiary)',
                  fontSize: 9.5,
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  marginBottom: 3,
                }}
              >
                result
              </div>
              <pre
                className="p-1.5 rounded overflow-auto"
                style={{
                  background: 'var(--color-code-bg, rgba(0,0,0,0.2))',
                  color: 'var(--color-text-secondary)',
                  fontSize: 11,
                  lineHeight: 1.4,
                  maxHeight: 180,
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                }}
              >
                {toolCall.result}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function formatJson(raw: string): string {
  try {
    return JSON.stringify(JSON.parse(raw), null, 2);
  } catch {
    return raw;
  }
}
