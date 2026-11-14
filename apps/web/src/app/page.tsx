"use client";

import { useCallback, useEffect, useState } from "react";
import AppShell from "./app-shell";
import SignInScreen from "./sign-in-screen";
import { clearSessionToken, getStoredSessionToken } from "@/lib/auth-session.mjs";
import { getClientConfig } from "@/lib/config";
import { loadIdentity } from "@/lib/sign-in.mjs";
import { getBrowserSupabaseClient } from "@/lib/supabase-browser";

/**
 * Landing route: restores an existing session when possible, otherwise shows
 * sign-in. On successful authentication, hands off to the authenticated app shell.
 */
export default function HomePage() {
  const supabaseClient = getBrowserSupabaseClient();
  const config = getClientConfig(process.env);
  const apiBaseUrl = config.apiBaseUrl;

  const [phase, setPhase] = useState("checking"); // checking | signed_out | ready
  const [identity, setIdentity] = useState(null);

  useEffect(() => {
    let cancelled = false;
    async function restore() {
      const token = getStoredSessionToken();
      if (!token) {
        if (!cancelled) setPhase("signed_out");
        return;
      }
      try {
        const me = await loadIdentity(apiBaseUrl);
        if (cancelled) return;
        setIdentity(me);
        setPhase("ready");
      } catch {
        clearSessionToken();
        if (!cancelled) setPhase("signed_out");
      }
    }
    restore();
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl]);

  const handleAuthenticated = useCallback((me) => {
    setIdentity(me);
    setPhase("ready");
  }, []);

  const handleSignOut = useCallback(() => {
    clearSessionToken();
    setIdentity(null);
    setPhase("signed_out");
  }, []);

  if (phase === "checking") {
    return (
      <main>
        <p>Loading…</p>
      </main>
    );
  }

  if (phase === "ready" && identity) {
    return (
      <AppShell
        apiBaseUrl={apiBaseUrl}
        initialIdentity={identity}
        onSignOut={handleSignOut}
      />
    );
  }

  return (
    <SignInScreen
      supabaseClient={supabaseClient}
      apiBaseUrl={apiBaseUrl}
      onAuthenticated={handleAuthenticated}
    />
  );
}
