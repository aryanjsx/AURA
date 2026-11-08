import { CheckCircle2, Circle, Loader2, MinusCircle } from 'lucide-react';
import type { ToolCallInfo } from '../../types';

export interface PlanStep {
  title: string;
  status: 'pending' | 'in_progress' | 'done' | 'skipped';
}

/** The plan from the latest `task_plan` call, or null if the agent made none. */
export function latestPlan(toolCalls: ToolCallInfo[] | undefined): PlanStep[] | null {
  const calls = (toolCalls ?? []).filter((tc) => tc.tool === 'task_plan');
  for (let i = calls.length - 1; i >= 0; i--) {
    try {
      const steps = JSON.parse(calls[i].arguments)?.steps;
      if (Array.isArray(steps) && steps.length > 0) {
        return steps
          .filter((s: any) => s && typeof s.title === 'string' && s.title.trim())
          .map((s: any) => ({
            title: s.title.trim(),
            status: ['pending', 'in_progress', 'done', 'skipped'].includes(s.status) ? s.status : 'pending',
          }));
      }
    } catch {
      /* keep looking at earlier calls */
    }
  }
  return null;
}

const icons = {
  pending: { icon: Circle, color: 'var(--color-text-tertiary)' },
  in_progress: { icon: Loader2, color: 'var(--color-accent)' },
  done: { icon: CheckCircle2, color: 'var(--color-success)' },
  skipped: { icon: MinusCircle, color: 'var(--color-text-tertiary)' },
};

export function TaskPlan({ steps, isLive }: { steps: PlanStep[]; isLive: boolean }) {
  const done = steps.filter((s) => s.status === 'done' || s.status === 'skipped').length;
  return (
    <div
      className="mb-3 rounded-md px-3 py-2 text-xs"
      style={{
        border: '1px solid var(--color-border-subtle, var(--color-border))',
        background: 'var(--color-bg-secondary)',
      }}
    >
      <div className="mb-1.5" style={{ color: 'var(--color-text-secondary)', fontWeight: 500 }}>
        Plan · {done} of {steps.length} done
      </div>
      <ol className="flex flex-col gap-1">
        {steps.map((step, i) => {
          const { icon: Icon, color } = icons[step.status];
          return (
            <li key={i} className="flex items-center gap-2">
              <Icon
                size={12}
                style={{ color, flexShrink: 0 }}
                className={step.status === 'in_progress' && isLive ? 'animate-spin' : ''}
              />
              <span
                style={{
                  color: step.status === 'pending' ? 'var(--color-text-secondary)' : 'var(--color-text)',
                  textDecoration: step.status === 'skipped' ? 'line-through' : undefined,
                }}
              >
                {step.title}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
