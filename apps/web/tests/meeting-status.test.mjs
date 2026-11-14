import assert from "node:assert/strict";
import test from "node:test";

import {
  describeMedia,
  describeTranscripts,
  isSessionError,
  selectLatestTranscript,
  summariseMedia,
} from "../src/lib/meeting-status.mjs";

test("summariseMedia reports an explicit empty state", () => {
  const summary = summariseMedia([]);
  assert.equal(summary.count, 0);
  assert.equal(summary.primaryStatus, null);
  assert.equal(summary.assetId, null);
  assert.equal(summary.hasValidated, false);
  assert.equal(describeMedia(summary), "No media yet — record or upload");
  assert.equal(describeMedia(null), "No media yet — record or upload");
});

test("summariseMedia summarises count, primary status and validation", () => {
  const summary = summariseMedia([
    { id: "asset-1", status: "validated" },
    { id: "asset-2", status: "processing" },
  ]);
  assert.equal(summary.count, 2);
  assert.equal(summary.primaryStatus, "validated");
  assert.equal(summary.assetId, "asset-1");
  assert.equal(summary.hasValidated, true);
  assert.equal(describeMedia(summary), "2 media · validated");
});

test("describeTranscripts renders empty and non-empty states", () => {
  assert.equal(describeTranscripts([]), "No transcripts yet");
  assert.equal(describeTranscripts(null), "No transcripts yet");
  assert.equal(describeTranscripts([{ id: "t1" }]), "1 transcript");
  assert.equal(
    describeTranscripts([{ id: "t1" }, { id: "t2" }]),
    "2 transcripts"
  );
});

test("selectLatestTranscript picks the newest by timestamp regardless of order", () => {
  const latest = selectLatestTranscript([
    { id: "old", updated_at: "2026-01-01T00:00:00Z" },
    { id: "newest", updated_at: "2026-06-01T00:00:00Z" },
    { id: "middle", created_at: "2026-03-01T00:00:00Z" },
  ]);
  assert.equal(latest.id, "newest");
});

test("selectLatestTranscript handles empty and missing timestamps", () => {
  assert.equal(selectLatestTranscript([]), null);
  assert.equal(selectLatestTranscript(undefined), null);
  const fallback = selectLatestTranscript([{ id: "only" }, { id: "also" }]);
  assert.ok(["only", "also"].includes(fallback.id));
});

test("isSessionError detects expiry and 401, ignores other failures", () => {
  assert.equal(isSessionError({ code: "session_expired" }), true);
  assert.equal(isSessionError({ status: 401, code: "request_failed" }), true);
  assert.equal(isSessionError({ status: 403, code: "forbidden" }), false);
  assert.equal(isSessionError(new Error("network down")), false);
  assert.equal(isSessionError(null), false);
});
