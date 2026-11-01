/**
 * Files attached to chat messages.
 *
 * The server reads each file (`POST /v1/attachments`) and returns extracted
 * text for documents or a resized JPEG for images. Conversations live in
 * localStorage, which holds only a few MB, so the message keeps just the
 * metadata and a small thumbnail; the full content goes to IndexedDB, keyed
 * by attachment id, and is read back when the conversation is sent again.
 */
import { authHeaders, getBase } from './api';
import type { AttachmentMeta } from '../types';

/** What `/v1/attachments` returns for one file. */
interface ServerAttachment {
  name: string;
  kind: 'document' | 'image' | 'unsupported';
  format: string;
  size: number;
  text?: string | null;
  truncated?: boolean;
  image?: string | null;
  width?: number | null;
  height?: number | null;
  note?: string | null;
}

/** The content sent to the model, kept out of localStorage. */
export interface AttachmentPayload {
  text?: string;
  image?: string;
}

export const MAX_FILES_PER_MESSAGE = 10;
export const MAX_FILE_BYTES = 25 * 1024 * 1024;

/** Upload files for reading. Throws with the server's message on failure. */
export async function readAttachments(
  files: File[],
): Promise<Array<{ meta: AttachmentMeta; payload: AttachmentPayload }>> {
  const form = new FormData();
  for (const file of files) form.append('files', file, file.name);
  const resp = await fetch(`${getBase()}/v1/attachments`, {
    method: 'POST',
    headers: authHeaders(),
    body: form,
  });
  if (!resp.ok) {
    let detail = `Upload failed (${resp.status})`;
    try {
      const body = await resp.json();
      if (typeof body?.detail === 'string') detail = body.detail;
    } catch {
      /* keep the status message */
    }
    throw new Error(detail);
  }
  const body: { attachments: ServerAttachment[] } = await resp.json();
  return Promise.all(
    body.attachments.map(async (a) => {
      const meta: AttachmentMeta = {
        id: crypto.randomUUID(),
        name: a.name,
        kind: a.kind,
        format: a.format,
        size: a.size,
        chars: a.text?.length,
        truncated: a.truncated || undefined,
        note: a.note || undefined,
        thumbnail: a.image ? await makeThumbnail(a.image) : undefined,
      };
      return { meta, payload: { text: a.text ?? undefined, image: a.image ?? undefined } };
    }),
  );
}

/** A small JPEG data URL for showing an image in the conversation. */
async function makeThumbnail(base64Jpeg: string, maxSide = 160): Promise<string | undefined> {
  try {
    const img = new Image();
    img.src = `data:image/jpeg;base64,${base64Jpeg}`;
    await img.decode();
    const scale = Math.min(1, maxSide / Math.max(img.width, img.height));
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(img.width * scale));
    canvas.height = Math.max(1, Math.round(img.height * scale));
    canvas.getContext('2d')?.drawImage(img, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL('image/jpeg', 0.7);
  } catch {
    return undefined;
  }
}

// ── IndexedDB storage for attachment content ───────────────────────────

const DB_NAME = 'locus-attachments';
const STORE = 'payloads';
/** Content of attachments added this session, so sends don't wait on IndexedDB. */
const memory = new Map<string, AttachmentPayload>();
let dbPromise: Promise<IDBDatabase> | null = null;

function openDb(): Promise<IDBDatabase> {
  if (!dbPromise) {
    dbPromise = new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, 1);
      req.onupgradeneeded = () => req.result.createObjectStore(STORE);
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }
  return dbPromise;
}

export async function savePayload(id: string, payload: AttachmentPayload): Promise<void> {
  memory.set(id, payload);
  try {
    const db = await openDb();
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite');
      tx.objectStore(STORE).put(payload, id);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  } catch {
    // Without IndexedDB the attachment still works for this session.
  }
}

export async function loadPayload(id: string): Promise<AttachmentPayload | undefined> {
  const cached = memory.get(id);
  if (cached) return cached;
  try {
    const db = await openDb();
    const payload = await new Promise<AttachmentPayload | undefined>((resolve, reject) => {
      const req = db.transaction(STORE, 'readonly').objectStore(STORE).get(id);
      req.onsuccess = () => resolve(req.result as AttachmentPayload | undefined);
      req.onerror = () => reject(req.error);
    });
    if (payload) memory.set(id, payload);
    return payload;
  } catch {
    return undefined;
  }
}

export async function deletePayloads(ids: string[]): Promise<void> {
  for (const id of ids) memory.delete(id);
  if (ids.length === 0) return;
  try {
    const db = await openDb();
    const tx = db.transaction(STORE, 'readwrite');
    for (const id of ids) tx.objectStore(STORE).delete(id);
  } catch {
    /* nothing to clean up */
  }
}

/** The chat API fields for one message's attachments. */
export async function apiAttachmentFields(attachments: AttachmentMeta[] | undefined): Promise<{
  images?: string[];
  attachments?: Array<{ name: string; format: string; text: string; truncated?: boolean; note?: string }>;
}> {
  if (!attachments?.length) return {};
  const images: string[] = [];
  const documents: Array<{ name: string; format: string; text: string; truncated?: boolean; note?: string }> = [];
  for (const meta of attachments) {
    const payload = await loadPayload(meta.id);
    if (meta.kind === 'image') {
      if (payload?.image) images.push(payload.image);
      else documents.push({ name: meta.name, format: meta.format, text: '', note: 'This image is no longer available on this device.' });
    } else if (meta.kind === 'document' && payload?.text !== undefined) {
      documents.push({ name: meta.name, format: meta.format, text: payload.text, truncated: meta.truncated, note: meta.note });
    } else {
      documents.push({
        name: meta.name,
        format: meta.format,
        text: '',
        note: meta.note || 'This file is no longer available on this device.',
      });
    }
  }
  return {
    ...(images.length ? { images } : {}),
    ...(documents.length ? { attachments: documents } : {}),
  };
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
