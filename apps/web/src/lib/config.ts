export interface NexusClientConfig {
  apiBaseUrl: string;
  supabaseUrl: string;
  supabaseAnonKey: string;
  voiceCloningEnabled: false;
}

/**
 * Fallback values for the Jotly Supabase project (ref: izxneacavxfcjklnsftd).
 *
 * These are PUBLIC-BY-DESIGN credentials: the Supabase anon key is shipped to
 * every browser that loads the app — embedding it here is equivalent to what a
 * NEXT_PUBLIC_* environment variable produces. It is NOT a secret.
 *
 * The service-role key and database password are NEVER referenced here; they
 * remain server-side only (.env on Hostinger, git-ignored, never committed).
 *
 * Environment variables still take precedence when present (e.g. Vercel
 * dashboard overrides or a future project swap).
 */
const FALLBACK_SUPABASE_URL = "https://izxneacavxfcjklnsftd.supabase.co";
const FALLBACK_SUPABASE_ANON_KEY =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Iml6eG5lYWNhdnhmY2prbG5zZnRkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTQ2MjAzMzAsImV4cCI6MjExMDE5NjMzMH0.FB-AlPLgP3krMMJncz4OMeee1LKehtChBecdNJzCIsU";

export function getClientConfig(env: Record<string, string | undefined> = {}): NexusClientConfig {
  return {
    apiBaseUrl: (env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1").replace(/\/+$/, ""),
    supabaseUrl: env.NEXT_PUBLIC_SUPABASE_URL || FALLBACK_SUPABASE_URL,
    supabaseAnonKey: env.NEXT_PUBLIC_SUPABASE_ANON_KEY || FALLBACK_SUPABASE_ANON_KEY,
    // Hard-locked false on client until Phase 6 server-side governance gates pass
    voiceCloningEnabled: false,
  };
}
