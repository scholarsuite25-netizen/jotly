/**
 * NEXUS API Client Builder (Vercel Web Client -> Cloudflare Edge -> Hostinger FastAPI)
 * Never trusts client-side role claims; all authorization and RLS isolation
 * are enforced server-side by the FastAPI backend.
 *
 * @param {{ accessToken: string; organisationId?: string; correlationId?: string }} options
 * @returns {Record<string, string>}
 */
export function buildAuthenticatedHeaders(options) {
  if (!options || !options.accessToken || !options.accessToken.trim()) {
    throw new Error(
      "Supabase Auth accessToken is required for authenticated API requests."
    );
  }

  /** @type {Record<string, string>} */
  const headers = {
    Authorization: `Bearer ${options.accessToken.trim()}`,
    "Content-Type": "application/json",
    "X-Correlation-ID": options.correlationId || crypto.randomUUID(),
  };

  if (options.organisationId && options.organisationId.trim()) {
    headers["X-Organisation-ID"] = options.organisationId.trim();
  }

  return headers;
}
