import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { fetchAgentPermissions, removeAgentPermission, type AgentPermission } from '../../lib/api';

const ACTION_WORDS: Record<string, string> = {
  set_volume: 'set the volume',
  mute: 'mute',
  unmute: 'unmute',
  set_brightness: 'set the brightness',
  dark_mode: 'switch to dark mode',
  light_mode: 'switch to light mode',
  lock_screen: 'lock the screen',
  open: 'open',
  close: 'close',
  read: 'read',
  write: 'write',
};

/** A rule in words, like "system_control: set the volume". */
export function describeRule(rule: AgentPermission): string {
  if (!rule.action) return `${rule.tool}: any use`;
  return `${rule.tool}: ${ACTION_WORDS[rule.action] ?? rule.action}`;
}

/** Agent mode's "always allow" rules, each with a Remove button. */
export function AgentPermissionsList() {
  const [rules, setRules] = useState<AgentPermission[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    fetchAgentPermissions()
      .then((r) => {
        setRules(r);
        setError(null);
      })
      .catch((err) => setError(err?.message || 'Could not load the rules.'));
  }, []);

  useEffect(load, [load]);

  const remove = async (key: string) => {
    try {
      await removeAgentPermission(key);
      setRules((prev) => (prev ?? []).filter((r) => r.key !== key));
    } catch (err: any) {
      toast.error(err?.message || 'Could not remove the rule.');
    }
  };

  if (error) {
    return <div className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>{error}</div>;
  }
  if (rules === null) {
    return <div className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>Loading…</div>;
  }
  if (rules.length === 0) {
    return (
      <div className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
        No steps are always allowed. Choose Always allow on an approval to add one. Commands and code always ask.
      </div>
    );
  }
  return (
    <ul className="flex flex-col">
      {rules.map((rule) => (
        <li
          key={rule.key}
          className="flex items-center justify-between py-2 text-sm"
          style={{ borderBottom: '1px solid var(--color-border-subtle)', color: 'var(--color-text)' }}
        >
          <span>{describeRule(rule)}</span>
          <button
            type="button"
            onClick={() => remove(rule.key)}
            className="px-2 py-0.5 rounded text-xs cursor-pointer"
            style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-secondary)' }}
          >
            Remove
          </button>
        </li>
      ))}
    </ul>
  );
}
