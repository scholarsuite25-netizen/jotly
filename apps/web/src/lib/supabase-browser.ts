import { createClient, SupabaseClient } from "@supabase/supabase-js";
import { getClientConfig } from "./config";

let browserClient: SupabaseClient | null = null;

/**
 * Returns a singleton Supabase browser client for the Vercel web app.
 * Uses only public (anon) credentials — the service-role key must NEVER be
 * referenced in client code or NEXT_PUBLIC_* variables.
 */
export function getBrowserSupabaseClient(): SupabaseClient {
  if (browserClient) {
    return browserClient;
  }
  const config = getClientConfig(
    typeof process !== "undefined" ? process.env : {}
  );
  browserClient = createClient(config.supabaseUrl, config.supabaseAnonKey, {
    auth: {
      persistSession: true,
      autoRefreshToken: true,
      detectSessionInUrl: true,
    },
  });
  return browserClient;
}
