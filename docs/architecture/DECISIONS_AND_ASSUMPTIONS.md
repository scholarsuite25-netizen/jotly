# 14 — Decisions, Assumptions and Open Questions

## 1. Working decisions from the supplied blueprint
- Product is standalone, not a Nexus Business Suite ERP module.
- Architecture must support SaaS and private/on-premises editions.
- Start with a modular monolith and separate workers/model services.
- Next.js/TypeScript web client and FastAPI backend are the recommended direction.
- PostgreSQL is the relational source of truth.
- Redis plus Celery or Dramatiq handles background jobs.
- S3-compatible private object storage is required.
- Keycloak or managed OIDC is the identity direction.
- Use local/self-hosted model candidates behind replaceable adapters.
- First release prioritises recording, transcription, editing, exports, document ingest, standard TTS, and playback.
- Voice cloning is consent-gated, private by default, revocable, audited, and disclosed.
- No performance claims before hardware/model benchmarking.

## 2. Assumptions requiring validation
- Initial launch jurisdiction(s) and legal review scope.
- Initial customer segment and pilot organisation.
- Exact supported audio/video/document formats and upload limits.
- Whether Keycloak is self-hosted or a managed OIDC provider is selected.
- Celery versus Dramatiq.
- MinIO or another S3-compatible storage provider.
- Exact ASR, diarisation, TTS, voice-cloning, and LLM versions.
- Pilot hardware, GPU availability, and expected concurrency.
- Retention defaults and legal-hold policy.
- Recording consent workflow per customer/jurisdiction.
- Whether user-facing participant consent collection is required in the first release.
- Pricing, quota, and support boundaries.
- Initial integration priorities.

## 3. Do not invent institutional policies
Where the blueprint does not specify a policy, keep it configurable and mark it for owner approval. Do not silently hard-code legal, retention, pricing, or customer-specific rules.

## 4. Architecture decision log
Use `DECISIONS.md` for each material technical or product decision. Include status, context, decision, alternatives, consequences, owner, and date.
