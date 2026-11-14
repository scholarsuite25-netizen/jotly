"use client";

import { useCallback, useMemo, useState } from "react";
import {
  createSignInState,
  loadIdentity,
  signIn,
  SIGNIN_STATES,
} from "@/lib/sign-in.mjs";

/**
 * Sign-in screen (client component).
 * Uses Supabase Auth via the injected client; on success hydrates /api/v1/me.
 * Server-side authorization remains the only authority — this screen carries no roles.
 * If the backend API is not reachable yet (e.g., Hostinger step pending), the user
 * still gets a signed-in state with a clear notice instead of a hard error.
 */
export default function SignInScreen({ supabaseClient, apiBaseUrl, onAuthenticated }) {
  const [state, setState] = useState(createSignInState);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const handleSubmit = useCallback(
    async (event) => {
      event.preventDefault();
      setState((prev) => ({ ...prev, state: SIGNIN_STATES.SUBMITTING, errorMessage: null }));
      try {
        const result = await signIn(supabaseClient, email, password);
        if (!result.ok) {
          setState((prev) => ({
            ...prev,
            state: SIGNIN_STATES.ERROR,
            errorMessage: result.message,
          }));
          return;
        }
        let identity = null;
        let backendNotice = null;
        try {
          identity = await loadIdentity(apiBaseUrl);
        } catch (apiError) {
          backendNotice =
            apiError.code === "session_expired"
              ? "Signed in, but the backend session check could not run yet."
              : "Signed in to Jotly. The meeting backend is not connected yet — it comes online at the Hostinger deployment step.";
        }
        if (identity && typeof onAuthenticated === "function") {
          onAuthenticated(identity);
          return;
        }
        setState((prev) => ({
          ...prev,
          state: SIGNIN_STATES.AUTHENTICATED,
          identity,
          backendNotice,
          errorMessage: null,
        }));
      } catch (error) {
        setState((prev) => ({
          ...prev,
          state: SIGNIN_STATES.ERROR,
          errorMessage: error.message || "Sign-in failed.",
        }));
      }
    },
    [apiBaseUrl, email, onAuthenticated, password, supabaseClient]
  );

  const submitting = useMemo(() => state.state === SIGNIN_STATES.SUBMITTING, [state.state]);

  if (state.state === SIGNIN_STATES.AUTHENTICATED) {
    const orgs = (state.identity && state.identity.organisations) || [];
    return (
      <main>
        <h1>Welcome back</h1>
        <p>Signed in as {state.identity ? state.identity.user.email : "your account"}.</p>
        {state.backendNotice ? (
          <p role="status">{state.backendNotice}</p>
        ) : null}
        {orgs.length > 0 ? (
          <ul aria-label="Organisation memberships">
            {orgs.map((org) => (
              <li key={org.id}>
                {org.name} ({org.roles.join(", ")})
              </li>
            ))}
          </ul>
        ) : null}
      </main>
    );
  }

  return (
    <main>
      <h1>Sign in to NEXUS Meeting Intelligence</h1>
      <form onSubmit={handleSubmit} aria-label="Sign in form">
        <label htmlFor="email">Email</label>
        <input
          id="email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          disabled={submitting}
        />
        <label htmlFor="password">Password</label>
        <input
          id="password"
          type="password"
          autoComplete="current-password"
          required
          minLength={8}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          disabled={submitting}
        />
        <button type="submit" disabled={submitting}>
          {submitting ? "Signing in…" : "Sign in"}
        </button>
        {state.errorMessage ? (
          <p role="alert" style={{ color: "#b00020" }}>
            {state.errorMessage}
          </p>
        ) : null}
      </form>
    </main>
  );
}
