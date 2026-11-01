/**
 * The user's name. The server keeps it in USER.md, which goes into every
 * system prompt, so the assistant calls the user by their nickname.
 */
import { authHeaders, getBase } from './api';

export interface UserProfile {
  first_name: string;
  last_name: string;
  nickname: string;
}

export const EMPTY_PROFILE: UserProfile = { first_name: '', last_name: '', nickname: '' };
export const MAX_NAME_LENGTH = 50;

/** The name Locus uses for the user: their nickname, else their first name. */
export function displayName(profile: UserProfile | null | undefined): string {
  return profile?.nickname || profile?.first_name || '';
}

async function detail(resp: Response, fallback: string): Promise<string> {
  try {
    const body = await resp.json();
    if (typeof body?.detail === 'string') return body.detail;
  } catch {
    /* use the fallback */
  }
  return fallback;
}

export async function fetchProfile(): Promise<UserProfile> {
  const resp = await fetch(`${getBase()}/v1/profile`, { headers: authHeaders() });
  if (!resp.ok) throw new Error(await detail(resp, `Could not load your name (${resp.status}).`));
  return resp.json();
}

export async function saveProfile(profile: UserProfile): Promise<UserProfile> {
  const resp = await fetch(`${getBase()}/v1/profile`, {
    method: 'PUT',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(profile),
  });
  if (!resp.ok) throw new Error(await detail(resp, `Could not save your name (${resp.status}).`));
  return resp.json();
}

const PROMPT_SEEN_KEY = 'locus-profile-prompt-seen';

interface ProfilePrompt {
  ready: boolean;
  open: () => void;
}

/** Ask for the user's name once, after desktop setup has finished. */
export function offerProfilePrompt({ ready, open }: ProfilePrompt): void {
  if (!ready || localStorage.getItem(PROMPT_SEEN_KEY)) return;
  localStorage.setItem(PROMPT_SEEN_KEY, 'true');
  open();
}
