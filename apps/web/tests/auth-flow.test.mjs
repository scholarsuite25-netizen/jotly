import assert from "node:assert/strict";
import test from "node:test";
import {
  clearSessionToken,
  getStoredSessionToken,
  getTokenExpiry,
  isTokenExpired,
  storeSessionToken,
} from "../src/lib/auth-session.mjs";
import { createSignInState, signIn, SIGNIN_STATES } from "../src/lib/sign-in.mjs";
import {
  createOrgSelectionState,
  organisationHeaders,
  selectOrganisation,
} from "../src/lib/org-selection.mjs";

// Minimal localStorage shim for Node test environment.
class LocalStorageShim {
  constructor() {
    this.map = new Map();
  }
  getItem(key) {
    return this.map.has(key) ? this.map.get(key) : null;
  }
  setItem(key, value) {
    this.map.set(key, String(value));
  }
  removeItem(key) {
    this.map.delete(key);
  }
}
globalThis.window = { localStorage: new LocalStorageShim() };

// Base64url JWT helper (unsigned body is fine: expiry preview only, server verifies signature).
function makeJwt(expSeconds) {
  const header = btoa(JSON.stringify({ alg: "HS256" }))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
  const payload = btoa(JSON.stringify({ exp: expSeconds }))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
  return `${header}.${payload}.sig`;
}

test("auth-session stores, reads, and clears the Supabase token", () => {
  assert.equal(storeSessionToken("  token-abc  "), true);
  assert.equal(getStoredSessionToken(), "token-abc");
  clearSessionToken();
  assert.equal(getStoredSessionToken(), null);
  assert.equal(storeSessionToken("   "), false);
});

test("auth-session expiry preview is client-side only and never grants access", () => {
  const futureExp = Math.floor(Date.now() / 1000) + 3600;
  const pastExp = Math.floor(Date.now() / 1000) - 10;
  const futureToken = makeJwt(futureExp);
  const pastToken = makeJwt(pastExp);

  assert.equal(isTokenExpired(futureToken), false);
  assert.equal(isTokenExpired(pastToken), true);
  assert.equal(isTokenExpired("garbage"), true);
  assert.ok(getTokenExpiry(futureToken) instanceof Date);
});

test("sign-in validates input, calls Supabase, stores token, and reports errors", async () => {
  let storedCalls = 0;
  const fakeSupabase = {
    auth: {
      async signInWithPassword({ email, password }) {
        if (email === "bad@org.example.com") {
          return { data: null, error: { message: "Invalid login credentials" } };
        }
        storedCalls += 1;
        return {
          data: { session: { access_token: makeJwt(Math.floor(Date.now() / 1000) + 600) } },
          error: null,
        };
      },
    },
  };

  let result = await signIn(fakeSupabase, "not-an-email", "longenough1");
  assert.equal(result.ok, false);
  assert.equal(result.errorCode, "invalid_email");

  result = await signIn(fakeSupabase, "user@org.example.com", "short");
  assert.equal(result.ok, false);
  assert.equal(result.errorCode, "weak_password");

  result = await signIn(fakeSupabase, "bad@org.example.com", "longenough1");
  assert.equal(result.ok, false);
  assert.equal(result.errorCode, "supabase_auth_error");
  assert.equal(result.message, "Invalid login credentials");

  result = await signIn(fakeSupabase, "user@org.example.com", "longenough1");
  assert.equal(result.ok, true);
  assert.equal(storedCalls, 1);
  assert.equal(getStoredSessionToken(), makeJwt(Math.floor(Date.now() / 1000) + 600));

  const state = createSignInState();
  assert.equal(state.state, SIGNIN_STATES.IDLE);
});

test("org-selection picks a membership, rejects unknown orgs, and builds headers", () => {
  const memberships = [
    { id: "org-a", name: "Org A" },
    { id: "org-b", name: "Org B" },
  ];
  let state = createOrgSelectionState(memberships);
  assert.equal(state.selectedOrgId, null);

  state = selectOrganisation(state, "org-b");
  assert.equal(state.selectedOrgId, "org-b");
  assert.deepEqual(organisationHeaders(state), { "X-Organisation-ID": "org-b" });

  state = selectOrganisation(state, "org-unknown");
  assert.equal(state.selectedOrgId, null);
  assert.match(state.error, /not in your memberships/);

  assert.throws(() => organisationHeaders(state), /Select an organisation/);
});
