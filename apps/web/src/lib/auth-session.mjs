/**
 * Supabase Auth session adapter (Vercel web client).
 * Manages JWT storage, expiry checks, and authenticated fetch wiring.
 * Authorization itself is ALWAYS enforced server-side; the client only carries the token.
 */

const TOKEN_STORAGE_KEY = "nexus_supabase_access_token";

export function storeSessionToken(token) {
  if (typeof window === "undefined" || !window.localStorage) {
    return false;
  }
  if (!token || !token.trim()) {
    return false;
  }
  window.localStorage.setItem(TOKEN_STORAGE_KEY, token.trim());
  return true;
}

export function getStoredSessionToken() {
  if (typeof window === "undefined" || !window.localStorage) {
    return null;
  }
  return window.localStorage.getItem(TOKEN_STORAGE_KEY);
}

export function clearSessionToken() {
  if (typeof window === "undefined" || !window.localStorage) {
    return;
  }
  window.localStorage.removeItem(TOKEN_STORAGE_KEY);
}

/**
 * Minimal JWT payload reader for expiry preview only.
 * The server verifies the signature; the client never trusts claims for authorization.
 */
export function getTokenExpiry(token) {
  if (!token || typeof token !== "string") {
    return null;
  }
  const parts = token.split(".");
  if (parts.length !== 3) {
    return null;
  }
  try {
    const payload = JSON.parse(atob(parts[1].replace(/-/g, "+").replace(/_/g, "/")));
    if (typeof payload.exp !== "number") {
      return null;
    }
    return new Date(payload.exp * 1000);
  } catch {
    return null;
  }
}

export function isTokenExpired(token, nowMs = Date.now()) {
  const expiry = getTokenExpiry(token);
  if (!expiry) {
    return true;
  }
  return expiry.getTime() <= nowMs;
}

/**
 * Authenticated fetch helper: attaches the stored Supabase token and returns
 * parsed JSON, normalising error envelopes into thrown errors.
 */
export async function authenticatedFetch(url, options = {}) {
  const token = getStoredSessionToken();
  if (!token || isTokenExpired(token)) {
    const error = new Error("Session expired. Please sign in again.");
    error.code = "session_expired";
    throw error;
  }

  const headers = {
    ...(options.headers || {}),
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };

  const response = await fetch(url, { ...options, headers });
  let body = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }

  if (!response.ok) {
    const error = new Error(
      (body && body.error && body.error.message) || `Request failed (${response.status})`
    );
    error.code = (body && body.error && body.error.code) || "request_failed";
    error.status = response.status;
    throw error;
  }
  return body;
}
