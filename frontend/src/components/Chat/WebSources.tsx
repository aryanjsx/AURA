import { Globe } from 'lucide-react';
import type { ResearchSource, WebSearchInfo } from '../../types';

interface Props {
  webSearch: WebSearchInfo;
  sources: ResearchSource[];
}

function hostOf(url?: string): string {
  if (!url) return '';
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
}

/** The pages a web search read for an answer, numbered like its citations. */
export function WebSources({ webSearch, sources }: Props) {
  return (
    <div className="mt-3 text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
      <div className="flex items-center gap-1.5 mb-1.5">
        <Globe size={12} />
        {webSearch.error ? (
          <span>Web search didn't work: {webSearch.error}</span>
        ) : (
          <span>
            Searched the web for <q>{webSearch.query}</q>
          </span>
        )}
      </div>
      {sources.length > 0 && (
        <ol className="flex flex-col gap-1">
          {sources.map((s) => (
            <li key={s.ref} className="flex gap-2 min-w-0">
              <span className="shrink-0 tabular-nums">[{s.ref}]</span>
              <a
                href={s.url}
                target="_blank"
                rel="noopener noreferrer"
                className="truncate hover:underline"
                style={{ color: 'var(--color-text-secondary)' }}
                title={s.url}
              >
                {s.title || hostOf(s.url)}
              </a>
              <span className="shrink-0">{hostOf(s.url)}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
