"use client";

import SignInScreen from "./sign-in-screen";
import { getBrowserSupabaseClient } from "@/lib/supabase-browser";
import { getClientConfig } from "@/lib/config";

/**
 * Landing route: renders the sign-in screen wired to the real Supabase project
 * (anon key only — public credentials) and the backend API base URL.
 */
export default function HomePage() {
  const supabaseClient = getBrowserSupabaseClient();
  const config = getClientConfig(process.env);

  return (
    <SignInScreen
      supabaseClient={supabaseClient}
      apiBaseUrl={config.apiBaseUrl}
    />
  );
}
