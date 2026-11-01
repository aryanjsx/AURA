import { AlertCircle, FileText, Loader2, X } from 'lucide-react';
import { formatBytes } from '../../lib/attachments';
import type { AttachmentMeta } from '../../types';

interface Props {
  name: string;
  meta?: AttachmentMeta;
  status?: 'reading' | 'ready' | 'error';
  error?: string;
  onRemove?: () => void;
}

/** One attached file: a thumbnail or file icon, its name, and what it is. */
export function AttachmentChip({ name, meta, status = 'ready', error, onRemove }: Props) {
  const problem = status === 'error' ? error : meta?.kind === 'unsupported' ? meta.note : undefined;
  const detail =
    status === 'reading'
      ? 'Reading...'
      : status === 'error'
        ? "Couldn't read"
        : meta
          ? [meta.format, formatBytes(meta.size), meta.truncated ? 'long, will be shortened' : '']
              .filter(Boolean)
              .join(' · ')
          : '';

  return (
    <div
      className="flex items-center gap-2 max-w-[16rem] pl-1.5 pr-2 py-1.5 rounded-lg text-xs"
      style={{
        background: 'var(--color-bg-secondary)',
        border: `1px solid ${problem ? 'var(--color-error)' : 'var(--color-border)'}`,
      }}
      title={problem || meta?.note || name}
    >
      {meta?.thumbnail ? (
        <img
          src={meta.thumbnail}
          alt=""
          className="w-8 h-8 rounded object-cover shrink-0"
        />
      ) : (
        <span
          className="w-8 h-8 rounded flex items-center justify-center shrink-0"
          style={{ background: 'var(--color-bg-tertiary)', color: 'var(--color-text-tertiary)' }}
        >
          {status === 'reading' ? (
            <Loader2 size={14} className="animate-spin" />
          ) : problem ? (
            <AlertCircle size={14} style={{ color: 'var(--color-error)' }} />
          ) : (
            <FileText size={14} />
          )}
        </span>
      )}
      <span className="min-w-0">
        <span className="block truncate font-medium" style={{ color: 'var(--color-text)' }}>
          {name}
        </span>
        <span className="block truncate" style={{ color: 'var(--color-text-tertiary)' }}>
          {detail}
        </span>
      </span>
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          aria-label={`Remove ${name}`}
          className="ml-auto p-0.5 rounded cursor-pointer shrink-0"
          style={{ color: 'var(--color-text-tertiary)' }}
        >
          <X size={12} />
        </button>
      )}
    </div>
  );
}
