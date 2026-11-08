import { useCallback, useEffect, useState } from 'react';
import { Loader2, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import {
  deleteModel,
  fetchInstalledModels,
  fetchModels,
  formatBytes,
  type InstalledModel,
} from '../lib/api';
import { nextModelAfterUninstall } from '../lib/model-capabilities';
import { useAppStore } from '../lib/store';

/**
 * Local models with their sizes, each with an Uninstall button that asks
 * first. Uninstalling the model chat is using switches chat to another one.
 */
export function InstalledModels() {
  const [models, setModels] = useState<InstalledModel[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [removing, setRemoving] = useState<string | null>(null);
  const selectedModel = useAppStore((s) => s.selectedModel);

  const load = useCallback(() => {
    fetchInstalledModels()
      .then((r) => {
        setModels(r.models);
        setError(null);
      })
      .catch((err) => setError(err?.message || 'Could not list installed models.'));
  }, []);

  useEffect(load, [load]);

  const uninstall = async (model: InstalledModel) => {
    setConfirming(null);
    setRemoving(model.name);
    try {
      const { freedBytes } = await deleteModel(model.name);
      const remaining = (models ?? []).filter((m) => m.name !== model.name);
      setModels(remaining);
      const app = useAppStore.getState();
      app.setModels(await fetchModels().catch(() => app.models));
      const next = nextModelAfterUninstall(
        app.selectedModel,
        model.name,
        useAppStore.getState().models.map((m) => m.id),
      );
      if (next !== null) app.setSelectedModel(next);
      app.addLogEntry({
        timestamp: Date.now(), level: 'info', category: 'model',
        message: `Uninstalled ${model.name}`,
      });
      const freed = freedBytes || model.size_bytes;
      toast.success(
        `Uninstalled ${model.name}${freed ? ` and freed ${formatBytes(freed)}` : ''}.` +
          (next ? ` Chat now uses ${next}.` : next === '' ? ' Download a model to keep chatting.' : ''),
      );
    } catch (err: any) {
      toast.error(err?.message || `Couldn't uninstall ${model.name}.`);
    } finally {
      setRemoving(null);
    }
  };

  if (error) {
    return <span className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>{error}</span>;
  }
  if (models === null) {
    return <span className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>Loading…</span>;
  }
  if (models.length === 0) {
    return <span className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>No models installed</span>;
  }

  return (
    <ul className="flex flex-col w-full">
      {models.map((model) => {
        const inUse = model.name === selectedModel;
        const busy = removing === model.name;
        return (
          <li
            key={model.name}
            className="flex items-center justify-between gap-3 py-1.5 text-sm"
            style={{ borderBottom: '1px solid var(--color-border-subtle)', color: 'var(--color-text)' }}
          >
            <span className="flex items-center gap-2 min-w-0">
              <span className="truncate">{model.name}</span>
              <span className="text-xs shrink-0" style={{ color: 'var(--color-text-tertiary)' }}>
                {formatBytes(model.size_bytes)}
              </span>
              {inUse && (
                <span
                  className="text-[10px] px-1.5 py-0.5 rounded-full shrink-0"
                  style={{ background: 'var(--color-accent-subtle)', color: 'var(--color-accent)' }}
                >
                  In use
                </span>
              )}
            </span>
            {confirming === model.name ? (
              <span className="flex items-center gap-1.5 shrink-0 text-xs">
                <span style={{ color: 'var(--color-text-secondary)' }}>
                  Uninstall and free {formatBytes(model.size_bytes)}?
                </span>
                <button
                  type="button"
                  onClick={() => uninstall(model)}
                  className="px-2 py-0.5 rounded cursor-pointer"
                  style={{ background: 'var(--color-error)', color: '#fff' }}
                >
                  Uninstall
                </button>
                <button
                  type="button"
                  onClick={() => setConfirming(null)}
                  className="px-2 py-0.5 rounded cursor-pointer"
                  style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-secondary)' }}
                >
                  Cancel
                </button>
              </span>
            ) : (
              <button
                type="button"
                onClick={() => setConfirming(model.name)}
                disabled={busy || removing !== null}
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs cursor-pointer disabled:cursor-default disabled:opacity-50 shrink-0"
                style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-secondary)' }}
                aria-label={`Uninstall ${model.name}`}
              >
                {busy ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={12} />}
                {busy ? 'Uninstalling…' : 'Uninstall'}
              </button>
            )}
          </li>
        );
      })}
    </ul>
  );
}
