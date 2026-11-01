import { useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';
import { useAppStore } from '../lib/store';
import {
  EMPTY_PROFILE,
  MAX_NAME_LENGTH,
  fetchProfile,
  saveProfile,
  type UserProfile,
} from '../lib/profile';

interface ProfileModalProps {
  onClose: () => void;
}

const FIELDS: Array<{ key: keyof UserProfile; label: string; placeholder: string; autoComplete: string }> = [
  { key: 'first_name', label: 'First name', placeholder: '', autoComplete: 'given-name' },
  { key: 'last_name', label: 'Last name', placeholder: '', autoComplete: 'family-name' },
  { key: 'nickname', label: 'Nickname', placeholder: 'What Locus should call you', autoComplete: 'nickname' },
];

/** Asks for the user's name so the assistant can address them by nickname. */
export function ProfileModal({ onClose }: ProfileModalProps) {
  const setProfile = useAppStore((s) => s.setProfile);
  const [form, setForm] = useState<UserProfile>(EMPTY_PROFILE);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const dialogRef = useRef<HTMLDivElement>(null);
  const firstFieldRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let active = true;
    fetchProfile()
      .then((profile) => { if (active) setForm(profile); })
      .catch(() => { /* start empty; saving reports any real problem */ })
      .finally(() => {
        if (!active) return;
        setLoading(false);
        firstFieldRef.current?.focus();
      });
    return () => { active = false; };
  }, []);

  const callThem = form.nickname.trim() || form.first_name.trim();

  const handleSave = async () => {
    if (saving || loading) return;
    setError('');
    setSaving(true);
    try {
      const saved = await saveProfile({
        first_name: form.first_name.trim(),
        last_name: form.last_name.trim(),
        nickname: form.nickname.trim(),
      });
      setProfile(saved);
      onClose();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not save your name.');
    } finally {
      setSaving(false);
    }
  };

  const busy = saving || loading;
  const inputStyle = {
    background: 'var(--color-bg-secondary)',
    border: '1px solid var(--color-border)',
    color: 'var(--color-text)',
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ backdropFilter: 'blur(8px)', background: 'rgba(0,0,0,0.4)' }}
      onClick={(event) => { if (event.target === event.currentTarget && !saving) onClose(); }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="profile-modal-title"
        className="relative w-full max-w-md mx-4 max-h-[90dvh] overflow-y-auto rounded-2xl p-4 sm:p-6"
        style={{
          background: 'var(--color-bg)',
          border: '1px solid var(--color-border)',
          boxShadow: '0 24px 80px rgba(0,0,0,0.25)',
        }}
        onKeyDown={(event) => {
          if (event.key === 'Escape' && !saving) onClose();
          if (event.key !== 'Tab') return;
          const controls = dialogRef.current?.querySelectorAll<HTMLElement>(
            'button:not([disabled]), input:not([disabled])',
          );
          if (!controls?.length) return;
          const first = controls[0];
          const last = controls[controls.length - 1];
          if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
          } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
          }
        }}
      >
        <button
          type="button"
          aria-label="Close"
          onClick={onClose}
          disabled={saving}
          className="absolute right-3 top-3 p-1.5 rounded-lg cursor-pointer"
          style={{ color: 'var(--color-text-tertiary)' }}
        ><X size={16} /></button>

        <h2
          id="profile-modal-title"
          className="text-lg font-semibold pr-6"
          style={{ color: 'var(--color-text)' }}
        >
          What should Locus call you?
        </h2>
        <p className="mt-1 text-sm" style={{ color: 'var(--color-text-secondary)' }}>
          Locus uses your nickname when it talks to you. Your name stays on this
          computer.
        </p>

        <form
          className="mt-5 flex flex-col gap-3"
          onSubmit={(event) => { event.preventDefault(); void handleSave(); }}
        >
          {FIELDS.map((field, i) => (
            <label key={field.key} className="flex flex-col gap-1 text-sm">
              <span style={{ color: 'var(--color-text-secondary)' }}>{field.label}</span>
              <input
                ref={i === 0 ? firstFieldRef : undefined}
                value={form[field.key]}
                onChange={(e) => setForm((f) => ({ ...f, [field.key]: e.target.value }))}
                placeholder={field.placeholder}
                autoComplete={field.autoComplete}
                maxLength={MAX_NAME_LENGTH}
                disabled={busy}
                className="rounded-xl px-3 py-2 outline-none"
                style={inputStyle}
              />
            </label>
          ))}

          <p className="text-xs min-h-[1rem]" style={{ color: 'var(--color-text-tertiary)' }}>
            {callThem ? <>Locus will call you <b style={{ color: 'var(--color-text)' }}>{callThem}</b>.</> : 'All fields are optional.'}
          </p>

          {error && (
            <p role="alert" className="text-xs" style={{ color: 'var(--color-error)' }}>{error}</p>
          )}

          <div className="mt-1 flex gap-2 justify-end">
            <button
              type="button"
              onClick={onClose}
              disabled={saving}
              className="min-h-10 rounded-xl px-4 py-2 text-sm font-medium cursor-pointer disabled:opacity-50"
              style={{ border: '1px solid var(--color-border)', color: 'var(--color-text)' }}
            >
              Not now
            </button>
            <button
              type="submit"
              disabled={busy}
              className="min-h-10 rounded-xl px-4 py-2 text-sm font-medium cursor-pointer disabled:opacity-50"
              style={{ background: 'var(--color-accent)', color: 'var(--color-on-accent)' }}
            >
              {saving ? 'Saving…' : 'Save'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
