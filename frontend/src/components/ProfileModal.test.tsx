import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../lib/store', () => ({
  useAppStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({ setProfile: vi.fn() }),
}));
vi.mock('../lib/profile', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib/profile')>()),
  fetchProfile: vi.fn(() => new Promise(() => {})),
}));

import { ProfileModal } from './ProfileModal';

describe('ProfileModal', () => {
  const html = renderToStaticMarkup(<ProfileModal onClose={() => {}} />);

  it('asks for first name, last name and nickname', () => {
    expect(html).toContain('What should Locus call you?');
    expect(html).toContain('First name');
    expect(html).toContain('Last name');
    expect(html).toContain('Nickname');
    expect(html).toMatch(/autocomplete="nickname"/i);
  });

  it('has no giveaway or sharing prompts', () => {
    expect(html).not.toMatch(/mac mini|giveaway|leaderboard|analytics/i);
    expect(html).toContain('Not now');
    expect(html).toContain('Save');
  });
});
