/**
 * Sign-in view model: orchestrates Supabase Auth sign-in against the configured
 * Supabase project and stores the resulting access token via auth-session.
 */
import { authenticatedFetch, storeSessionToken } from "./auth-session.mjs";

export const SIGNIN_STATES = Object.freeze({
  IDLE: "idle",
  SUBMITTING: "submitting",
  AUTHENTICATED: "authenticated",
  ERROR: "error",
});

export function createSignInState() {
  return {
    state: SIGNIN_STATES.IDLE,
    errorMessage: null,
    identity: null,
  };
}

/**
 * Performs password sign-in through the backend's Supabase-backed auth endpoint.
 * `supabaseClientLike` must expose `signInWithPassword({ email, password })`.
 */
export async function signIn(supabaseClientLike, email, password) {
  if (!email || !email.includes("@")) {
    return { ok: false, errorCode: "invalid_email", message: "Enter a valid email address." };
  }
  if (!password || password.length < 8) {
    return {
      ok: false,
      errorCode: "weak_password",
      message: "Password must be at least 8 characters.",
    };
  }

  const { data, error } = await supabaseClientLike.auth.signInWithPassword({
    email: email.trim().toLowerCase(),
    password,
  });
  if (error) {
    return { ok: false, errorCode: "supabase_auth_error", message: error.message };
  }

  const accessToken = data && data.session && data.session.access_token;
  if (!accessToken) {
    return {
      ok: false,
      errorCode: "no_session_token",
      message: "Sign-in succeeded but no access token was returned.",
    };
  }

  storeSessionToken(accessToken);
  return { ok: true, accessToken };
}

/** Fetches /api/v1/me to hydrate the authenticated identity + organisation context. */
export async function loadIdentity(apiBaseUrl) {
  return authenticatedFetch(`${apiBaseUrl.replace(/\/+$/, "")}/me`);
}
