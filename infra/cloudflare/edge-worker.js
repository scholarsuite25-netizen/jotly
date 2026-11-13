/**
 * Cloudflare Backend Edge Gateway Worker
 * Fronts the self-hosted FastAPI backend on Hostinger VPS.
 * Enforces correlation IDs, strict security headers, and Vercel CORS origins.
 */
export default {
  async fetch(request, env) {
    const correlationId =
      request.headers.get("X-Correlation-ID") || crypto.randomUUID();
    const origin = request.headers.get("Origin") || "";
    const allowedOrigins = (env.ALLOWED_VERCEL_ORIGIN || "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);

    if (request.method === "OPTIONS") {
      const headers = new Headers();
      if (allowedOrigins.includes(origin)) {
        headers.set("Access-Control-Allow-Origin", origin);
        headers.set("Access-Control-Allow-Credentials", "true");
      }
      headers.set(
        "Access-Control-Allow-Methods",
        "GET, POST, PATCH, PUT, DELETE, OPTIONS"
      );
      headers.set(
        "Access-Control-Allow-Headers",
        "Authorization, Content-Type, X-Correlation-ID, X-Organisation-ID, Idempotency-Key"
      );
      headers.set("X-Correlation-ID", correlationId);
      return new Response(null, { status: 204, headers });
    }

    const targetUrl = new URL(request.url);
    const upstreamBase = new URL(env.HOSTINGER_ORIGIN_URL);
    targetUrl.protocol = upstreamBase.protocol;
    targetUrl.host = upstreamBase.host;

    const upstreamHeaders = new Headers(request.headers);
    upstreamHeaders.set("X-Correlation-ID", correlationId);
    if (env.CLOUDFLARE_EDGE_SHARED_SECRET) {
      upstreamHeaders.set(
        "X-Cloudflare-Origin-Secret",
        env.CLOUDFLARE_EDGE_SHARED_SECRET
      );
    }

    const upstreamRequest = new Request(targetUrl.toString(), {
      method: request.method,
      headers: upstreamHeaders,
      body:
        request.method !== "GET" && request.method !== "HEAD"
          ? request.body
          : undefined,
      redirect: "manual",
    });

    const response = await fetch(upstreamRequest);
    const responseHeaders = new Headers(response.headers);
    responseHeaders.set("X-Correlation-ID", correlationId);
    responseHeaders.set("X-Content-Type-Options", "nosniff");
    responseHeaders.set("X-Frame-Options", "DENY");
    responseHeaders.set("Referrer-Policy", "strict-origin-when-cross-origin");
    responseHeaders.set(
      "Strict-Transport-Security",
      "max-age=63072000; includeSubDomains; preload"
    );

    if (allowedOrigins.includes(origin)) {
      responseHeaders.set("Access-Control-Allow-Origin", origin);
      responseHeaders.set("Access-Control-Allow-Credentials", "true");
    }

    return new Response(response.body, {
      status: response.status,
      headers: responseHeaders,
    });
  },
};
