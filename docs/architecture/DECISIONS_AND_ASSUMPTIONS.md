# 14 — Decisions, Assumptions and Open Questions

## 1. Working decisions from the supplied blueprint and owner direction
- Product is standalone, not a Nexus Business Suite ERP module.
- Architecture must support SaaS and private/on-premises editions.
- **Delivery & DevOps path:** OpenCode (primary implementation) → GitHub (source of truth & CI/CD gates) → Vercel (Next.js web frontend) + Cloudflare (backend edge gateway, WAF, Zero Trust Tunnel, rate limiting, R2-compatible private storage) + Hostinger VPS Self-Hosting (Docker Compose running FastAPI modular monolith, background workers, Redis, and local AI/media adapters).
- Start with a modular monolith and separate workers/model services.
- Next.js/TypeScript web client and FastAPI backend are the approved application stack.
- PostgreSQL is the relational source of truth with Row-Level Security (RLS).
- **Authentication:** Supabase Auth (`SUPABASE_URL`, `SUPABASE_JWT_SECRET` / JWKS) is the approved identity provider, with server-side tenant membership verification in FastAPI.
- **Transactional Email:** Multi-provider adapter supporting **Resend**, **Emailbump**, and **Unipost** with configurable primary and automatic fallback.
- Redis plus Dramatiq/Celery handles background jobs with explicit tenant context propagation.
- S3-compatible private object storage (Cloudflare R2 / MinIO) is required.
- Use local/self-hosted model candidates behind replaceable adapters, with deterministic stub adapters for CI and CPU-only testing.
- First release prioritises recording, transcription, editing, exports, document ingest, standard TTS, and playback.
- Voice cloning is consent-gated, private by default, revocable, audited, and disclosed (`VOICE_CLONING_ENABLED=false` until Phase 6 gates pass).
- No performance claims before hardware/model benchmarking.

## 2. Assumptions requiring validation
- Initial launch jurisdiction(s) and legal review scope.
- Initial customer segment and pilot organisation.
- Exact supported audio/video/document formats and upload limits (configurable defaults set in ADR-004).
- Exact ASR, diarisation, TTS, voice-cloning, OCR, and LLM model versions.
- Hostinger VPS hardware sizing, GPU availability, and expected concurrency.
- Retention defaults and legal-hold policy.
- Recording consent workflow per customer/jurisdiction.
- Whether user-facing participant consent collection is required in the first release.
- Pricing, quota, and support boundaries.
- Initial integration priorities.

## 3. Do not invent institutional policies
Where the blueprint does not specify a policy, keep it configurable and mark it for owner approval. Do not silently hard-code legal, retention, pricing, or customer-specific rules.

## 4. Architecture decision log
Use `docs/architecture/DECISION_LOG.md` for each material technical or product decision. Include status, context, decision, alternatives, consequences, owner, and date.
