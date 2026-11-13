import assert from "node:assert/strict";
import test from "node:test";
import { buildAuthenticatedHeaders } from "../src/lib/api-client.mjs";

test("buildAuthenticatedHeaders attaches Bearer token, correlation ID, and optional X-Organisation-ID", () => {
  const headers = buildAuthenticatedHeaders({
    accessToken: "supa-jwt-token",
    organisationId: "org-123",
    correlationId: "corr-001",
  });

  assert.equal(headers.Authorization, "Bearer supa-jwt-token");
  assert.equal(headers["X-Organisation-ID"], "org-123");
  assert.equal(headers["X-Correlation-ID"], "corr-001");
});

test("buildAuthenticatedHeaders rejects empty accessToken", () => {
  assert.throws(
    () => buildAuthenticatedHeaders({ accessToken: "   " }),
    /Supabase Auth accessToken is required/
  );
});
