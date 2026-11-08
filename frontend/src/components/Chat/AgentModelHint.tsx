import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { fetchAgentModel, fetchModels, pullModel, type AgentModelRecommendation } from '../../lib/api';
import { modelSizeBillions, shouldSuggestAgentModel } from '../../lib/model-capabilities';
import { useAppStore } from '../../lib/store';

/**
 * In Agent mode with a small model, suggest the model that works best on
 * this computer, with one click to use it (downloading it first if needed).
 */
export function AgentModelHint({ selectedModel }: { selectedModel: string }) {
  const [rec, setRec] = useState<AgentModelRecommendation | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchAgentModel()
      .then((r) => {
        if (!cancelled) setRec(r);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  if (!rec) return null;
  if (!rec.model) {
    if (modelSizeBillions(selectedModel) === null) return null;
    return (
      <div className="text-[11px] leading-snug" style={{ color: 'var(--color-text-tertiary)' }}>
        {rec.reason}
      </div>
    );
  }
  if (!shouldSuggestAgentModel(selectedModel, rec.model)) return null;

  const useIt = async () => {
    const app = useAppStore.getState();
    if (rec.installed) {
      app.setSelectedModel(rec.model);
      return;
    }
    setBusy(true);
    const id = toast.loading(`Downloading ${rec.model}. This can take a few minutes…`);
    try {
      await pullModel(rec.model);
      app.setModels(await fetchModels());
      app.setSelectedModel(rec.model);
      setRec({ ...rec, installed: true });
      toast.success(`Now using ${rec.model} for Agent mode.`, { id });
    } catch (err: any) {
      toast.error(err?.message || `Couldn't download ${rec.model}.`, { id });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="flex flex-wrap items-center gap-2 text-[11px] leading-snug"
      style={{ color: 'var(--color-text-tertiary)' }}
    >
      <span>
        {selectedModel} often misses tool calls. {rec.reason}
      </span>
      <button
        type="button"
        onClick={useIt}
        disabled={busy}
        className="px-2 py-0.5 rounded-md cursor-pointer disabled:cursor-default disabled:opacity-50"
        style={{ border: '1px solid var(--color-accent)', color: 'var(--color-accent)' }}
      >
        {busy ? 'Downloading…' : rec.installed ? `Use ${rec.model}` : `Download and use ${rec.model}`}
      </button>
    </div>
  );
}
