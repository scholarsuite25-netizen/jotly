/**
 * Meeting discovery view-model helpers (Phase A UX polish).
 * Pure functions used by the dashboard to summarise per-meeting media and
 * transcripts, pick the newest transcript, and detect session-expiry errors so
 * the shell can force a clean re-authentication. Authorization itself always
 * stays server-side; these helpers only shape what the UI displays.
 */

/** Summarise a meeting's media assets for the dashboard media column. */
export function summariseMedia(mediaItems) {
  const items = Array.isArray(mediaItems) ? mediaItems : [];
  const primary = items.length > 0 ? items[0] : null;
  return {
    count: items.length,
    primaryStatus: primary && primary.status ? primary.status : null,
    assetId: primary ? primary.id : null,
    hasValidated: items.some((item) => item && item.status === "validated"),
  };
}

/** Human-readable media cell text, including an explicit empty state. */
export function describeMedia(summary) {
  if (!summary || summary.count === 0) {
    return "No media yet — record or upload";
  }
  const status = summary.primaryStatus || "unknown status";
  return summary.count === 1
    ? `1 media · ${status}`
    : `${summary.count} media · ${status}`;
}

/**
 * Pick the most recent transcript from an API list (already sorted newest
 * server-side, but re-sorted defensively on timestamp so ordering mistakes in
 * the client never surface as "oldest transcript opened").
 */
export function selectLatestTranscript(transcripts) {
  const items = Array.isArray(transcripts) ? transcripts : [];
  if (items.length === 0) {
    return null;
  }
  const timestamp = (item) => {
    const raw = item && (item.updated_at || item.created_at);
    const parsed = raw ? Date.parse(raw) : NaN;
    return Number.isNaN(parsed) ? 0 : parsed;
  };
  return [...items].sort((a, b) => timestamp(b) - timestamp(a))[0];
}

/** Explicit empty state for the transcripts column. */
export function describeTranscripts(transcripts) {
  const items = Array.isArray(transcripts) ? transcripts : [];
  if (items.length === 0) {
    return "No transcripts yet";
  }
  return items.length === 1 ? "1 transcript" : `${items.length} transcripts`;
}

/**
 * True when an authenticatedFetch error means the session is gone (expired
 * token or server-side 401). The shell reacts by clearing the token and
 * returning to sign-in instead of leaving the user on a broken screen.
 */
export function isSessionError(err) {
  if (!err) {
    return false;
  }
  return err.code === "session_expired" || err.status === 401;
}
