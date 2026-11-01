export const SUPABASE_URL =
  import.meta.env.VITE_SUPABASE_URL ?? '';

// The Supabase anon key is optional at build time. When it is unset the public
// savings leaderboard is disabled rather than failing the build — this keeps
// the `locus` package and desktop app buildable without coupling
// publishability to a leaderboard credential. Set VITE_SUPABASE_ANON_KEY at
// build time (from a repo secret) to enable the leaderboard.
export const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY ?? '';

export const LEADERBOARD_ENABLED = SUPABASE_URL.length > 0 && SUPABASE_ANON_KEY.length > 0;
