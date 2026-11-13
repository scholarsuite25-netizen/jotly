# Architecture Decision Records

Use one section per material decision. Keep accepted decisions stable; supersede them with a new record rather than silently rewriting history.

## ADR-000 — Documentation baseline

- **Status:** Accepted as working baseline
- **Date:** 2026-11-13
- **Context:** Supplied NEXUS Meeting Intelligence product and engineering blueprint.
- **Decision:** Use this Markdown pack as the initial implementation documentation. Preserve the source blueprint's product boundaries, phased delivery, technology direction, and safeguards.
- **Consequences:** Unspecified customer policies, exact versions, infrastructure sizing, pricing, and jurisdiction-specific legal interpretations remain open and configurable.

## ADR-001 — Delivery & Hosting Topology (OpenCode → GitHub → Vercel + Cloudflare + Hostinger Self-Hosting)
- **Status:** Accepted
- **Date:** 2026-11-13
- **Owner:** Project Owner
- **Context:** The project requires an automated, repeatable development and deployment pipeline supporting SaaS web delivery alongside self-hosted backend and AI/media worker compute.
- **Decision:**
  1. **OpenCode** serves as the primary implementation environment; **GitHub** is the canonical source-code repository and CI/CD orchestrator.
  2. **Vercel** deploys and serves the Next.js Web Client (`apps/web`).
  3. **Cloudflare** protects and fronts the backend API and object storage layer (Cloudflare DNS, WAF, Rate Limiting, Zero Trust Tunnel `cloudflared`, and optional Cloudflare R2 S3-compatible private storage).
  4. **Hostinger VPS (Self-Hosting)** runs the containerised FastAPI application (`apps/api`), background job workers, Redis, PostgreSQL (or Supabase Postgres), and local media/AI model services via Docker Compose (`infra/hostinger/docker-compose.hostinger.yml`).
- **Alternatives considered:** Single-vendor cloud PaaS; raw Kubernetes cluster (rejected as premature complexity).
- **Consequences:** Clean separation between globally cached frontend assets on Vercel, edge DDoS/WAF protection on Cloudflare, and predictable self-hosted compute on Hostinger VPS.
- **Validation required:** CI build checks, Cloudflare origin protection verification, and Hostinger Docker Compose health checks.

## ADR-002 — Authentication via Supabase Auth & Multi-Tenant PostgreSQL RLS Context
- **Status:** Accepted
- **Date:** 2026-11-13
- **Owner:** Project Owner
- **Context:** Every API request and background job must resolve user identity and verify active organisation membership server-side before accessing tenant data.
- **Decision:**
  1. **Supabase Auth** (`SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_JWT_SECRET` / JWKS) is the identity provider.
  2. FastAPI validates Supabase JWT tokens (`sub`, `email`, `exp`, `aud`, and `aal` claim for administrator MFA enforcement), synchronises/resolves the internal `users` and `sessions` records, and verifies active membership in the target `organisation_id` against `user_roles` in PostgreSQL.
  3. Client-supplied `X-Organisation-ID` or path `org_id` parameters are **never trusted** until confirmed against active database membership. Unauthorised tenant access attempts are rejected with `403 Forbidden` and logged as security audit events.
  4. For every tenant-scoped database transaction, the backend sets `SET LOCAL app.current_organisation_id = '<verified_org_uuid>'` and `SET LOCAL app.current_user_id = '<verified_user_uuid>'`. PostgreSQL Row-Level Security (RLS) policies (`ENABLE ROW LEVEL SECURITY` + `FORCE ROW LEVEL SECURITY`) enforce tenant isolation at the database layer, reinforced by repository-level `organisation_id` predicates.
- **Alternatives considered:** Self-hosted Keycloak only (retained as an on-prem OIDC option behind the same JWT verification interface).
- **Consequences:** Zero trust for client tenant claims; defense-in-depth between FastAPI authorisation dependencies and PostgreSQL RLS.
- **Validation required:** Automated cross-tenant denial tests (`test_rls_isolation.py`, `test_auth_permissions.py`).

## ADR-003 — Multi-Provider Transactional Email Adapter (Resend, Emailbump, Unipost)
- **Status:** Accepted
- **Date:** 2026-11-13
- **Owner:** Project Owner
- **Context:** Organisation invitations, role notifications, and security alerts require reliable transactional email delivery with failover and strict privacy guarantees.
- **Decision:** Implement a narrow server-side `EmailService` adapter supporting **Resend**, **Emailbump**, and **Unipost** in a configurable priority chain (`EMAIL_PRIMARY_PROVIDER=resend`, `EMAIL_FALLBACK_PROVIDERS=emailbump,unipost`). Email payloads are strictly sanitised so raw transcripts, audio URLs, voice samples, or secrets can never be included in email bodies or subjects.
- **Alternatives considered:** Single hardcoded SMTP/API provider.
- **Consequences:** High deliverability with automatic provider failover and deterministic local/CI capture testing.
- **Validation required:** Unit tests verifying provider routing, automatic failover across Resend/Emailbump/Unipost, and sensitive-content redaction.

## ADR-004 — Phase 1 Canonical Schema, API Error Envelope & Configurable Defaults
- **Status:** Accepted
- **Date:** 2026-11-13
- **Owner:** Project Owner
- **Context:** Close specification gaps around Phase 1 table columns, API envelopes, and default limits prior to migrations.
- **Decision:**
  1. **Phase 1 Tables:** `organisations`, `workspaces`, `departments`, `users`, `roles`, `permissions`, `user_roles`, `role_permissions`, `invitations`, `sessions`, `audit_logs`, `background_jobs` created via reversible Alembic migration `0001_phase1_foundation_and_rls.py`.
  2. **Standard Error Envelope:** All `/api/v1` errors return `{"error": {"code": "...", "message": "...", "correlation_id": "..."}}` with matching `X-Correlation-ID` response header.
  3. **Configurable Defaults:** Upload chunk size = `5 MB`, presigned URL TTL = `300s`, voice cloning gate `VOICE_CLONING_ENABLED=false` (hard-locked off until Phase 6 governance sign-off).
- **Validation required:** Migration upgrade/downgrade inspection and API contract tests.

## ADR-005 — SDLC, DevOps, General Testing Strategy & Tamper-Evident Audit Chain
- **Status:** Accepted
- **Date:** 2026-11-13
- **Owner:** Project Owner
- **Context:** Enterprise meeting and voice intelligence requires strict SDLC gates, automated DevOps checks, multi-layer testing, and tamper-evident audit logging.
- **Decision:**
  1. **SDLC & DevOps Gates:** Every branch must pass automated GitHub Actions CI (`.github/workflows/ci.yml`) executing secret scanning, Python lint/type/unit/integration/RLS security tests (`pytest`), Next.js type/unit tests (`vitest`), migration verification, and SBOM/licence register validation before merge or deployment to Vercel/Cloudflare/Hostinger.
  2. **General Testing Matrix:** Enforce unit tests (permissions, config, email failover, audit redaction), integration tests (API endpoints, DB sessions), negative security tests (cross-tenant IDOR, unauthenticated calls, privilege escalation, worker tenant mismatch), and PostgreSQL RLS policy verification.
  3. **Tamper-Evident Audit Architecture:** Every sensitive action writes an immutable `AuditLog` record containing `actor_id`, `organisation_id`, `action`, `resource_type`, `resource_id`, `result`, `correlation_id`, sanitised metadata, `previous_hash`, and `entry_hash` (`SHA-256` cryptographic hash chain per organisation) with an integrity verification routine (`verify_audit_chain`) to detect any unauthorized tampering.
- **Validation required:** Automated test suite execution and audit chain tamper-detection tests.

## ADR template

### ADR-XXX — [Decision title]
- **Status:** Proposed / Accepted / Rejected / Superseded
- **Date:**
- **Owner:**
- **Context:** What problem or decision is being addressed?
- **Decision:** What has been selected?
- **Alternatives considered:**
- **Consequences:** Benefits, costs, risks, migration impact.
- **Validation required:** Tests, benchmarks, legal/licence review, stakeholder approval.
