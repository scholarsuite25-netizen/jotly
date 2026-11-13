export interface NexusClientConfig {
  apiBaseUrl: string;
  supabaseUrl: string;
  supabaseAnonKey: string;
  voiceCloningEnabled: false;
}

export function getClientConfig(env: Record<string, string | undefined> = {}): NexusClientConfig {
  return {
    apiBaseUrl: (env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1").replace(/\/+$/, ""),
    supabaseUrl: env.NEXT_PUBLIC_SUPABASE_URL || "https://your-project-ref.supabase.co",
    supabaseAnonKey: env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "supabase-anon-placeholder",
    // Hard-locked false on client until Phase 6 server-side governance gates pass
    voiceCloningEnabled: false,
  };
}
