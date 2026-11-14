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
 */
export default function SignInScreen({ supabaseClient, apiBaseUrl }) {
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
        const identity = await loadIdentity(apiBaseUrl);
        setState((prev) => ({
          ...prev,
          state: SIGNIN_STATES.AUTHENTICATED,
          identity,
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
    [apiBaseUrl, email, password, supabaseClient]
  );

  const submitting = useMemo(() => state.state === SIGNIN_STATES.SUBMITTING, [state.state]);

  if (state.state === SIGNIN_STATES.AUTHENTICATED) {
    const orgs = (state.identity && state.identity.organisations) || [];
    return (
      <main>
        <h1>Welcome back</h1>
        <p>Signed in as {state.identity.user.email}</p>
        <ul aria-label="Organisation memberships">
          {orgs.map((org) => (
            <li key={org.id}>
              {org.name} ({org.roles.join(", ")})
            </li>
          ))}
        </ul>
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
