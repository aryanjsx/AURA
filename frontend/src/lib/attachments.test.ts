import { describe, expect, it } from 'vitest';
import { apiAttachmentFields, formatBytes, savePayload } from './attachments';
import type { AttachmentMeta } from '../types';

const meta = (over: Partial<AttachmentMeta>): AttachmentMeta => ({
  id: crypto.randomUUID(),
  name: 'file',
  kind: 'document',
  format: 'text',
  size: 10,
  ...over,
});

describe('apiAttachmentFields', () => {
  it('is empty without attachments', async () => {
    expect(await apiAttachmentFields(undefined)).toEqual({});
    expect(await apiAttachmentFields([])).toEqual({});
  });

  it('sends images and documents from saved content', async () => {
    const image = meta({ name: 'photo.png', kind: 'image', format: 'PNG image' });
    const doc = meta({ name: 'notes.md', format: 'MD file', truncated: true });
    await savePayload(image.id, { image: 'aGVsbG8=' });
    await savePayload(doc.id, { text: '# Notes' });

    expect(await apiAttachmentFields([image, doc])).toEqual({
      images: ['aGVsbG8='],
      attachments: [{ name: 'notes.md', format: 'MD file', text: '# Notes', truncated: true, note: undefined }],
    });
  });

  it('describes files it can no longer find or read', async () => {
    const gone = meta({ name: 'old.pdf', format: 'PDF' });
    const binary = meta({ name: 'a.bin', kind: 'unsupported', format: 'BIN file', note: 'Binary file.' });
    const result = await apiAttachmentFields([gone, binary]);
    expect(result.images).toBeUndefined();
    expect(result.attachments).toEqual([
      { name: 'old.pdf', format: 'PDF', text: '', note: 'This file is no longer available on this device.' },
      { name: 'a.bin', format: 'BIN file', text: '', note: 'Binary file.' },
    ]);
  });
});

describe('formatBytes', () => {
  it('uses B, KB and MB', () => {
    expect(formatBytes(512)).toBe('512 B');
    expect(formatBytes(2048)).toBe('2 KB');
    expect(formatBytes(3.5 * 1024 * 1024)).toBe('3.5 MB');
  });
});
