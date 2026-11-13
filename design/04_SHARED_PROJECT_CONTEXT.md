# Shared Project Context — NEXUS Meeting Intelligence

## Purpose
This is the compact orientation document both OpenCode and Antigravity must read before substantial work. The detailed product and technical specifications remain authoritative for their respective subjects.

## Product identity
NEXUS Meeting Intelligence is the product described by the approved blueprint and the requirements in this repository. Do not add capabilities, pricing, integrations, or policies not supported by the approved requirements or a recorded owner decision.

## Canonical sources
- `README.md`: repository map, getting started and document index.
- `docs/product/PRODUCT_REQUIREMENTS.md`: product scope and requirements.
- `docs/architecture/SYSTEM_ARCHITECTURE.md`: architecture principles and system boundaries.
- `docs/data-and-api/DOMAIN_MODEL_AND_DATABASE.md`: domain entities and persistence.
- `docs/data-and-api/API_AND_INTEGRATION_CONTRACTS.md`: interfaces and external integrations.
- `docs/security-and-privacy/SECURITY_THREAT_MODEL.md`: threat and security controls.
- `docs/security-and-privacy/PRIVACY_RECORDING_AND_VOICE_CONSENT.md`: recording, consent and voice governance.
- `docs/architecture/DECISIONS_AND_ASSUMPTIONS.md` and `docs/architecture/DECISION_LOG.md`: decisions and unresolved assumptions.
- `docs/quality-and-operations/`: testing, acceptance, deployment, DevOps, and licence governance.
- `design/`: multi-agent collaboration operating rules.

If documents conflict, do not choose silently. Identify the conflict, cite the affected sections, and request owner direction or record a proposed resolution for approval.

## Technology choices
Use the stack explicitly established in the current repository and blueprint. Do not silently substitute frameworks, databases, hosting providers, AI services, or media pipelines. If the repository differs from the documentation, report the difference and propose a reconciliation.

## Agent behavior
- Inspect before modifying.
- Prefer small, reversible, testable changes.
- Preserve existing conventions unless an approved change says otherwise.
- Do not create duplicate implementations of auth, tenancy, storage, transcription, document generation, or voice governance.
- Do not expose secrets in code, logs, screenshots, prompts, or documentation.
- Treat recordings, transcripts, meeting documents and voice profiles as sensitive user content.
- Record assumptions and decisions rather than inventing policy.

## Current work snapshot
Keep this section updated by the project owner or lead agent:
- Current release/milestone: Phase 2 — Recording and Media (Completed).
- Active branch: `feat/phase-2-recording-media`
- Approved delivery & hosting path: OpenCode → GitHub (CI/CD, SDLC gates) → Vercel (`apps/web`) + Cloudflare (Backend Edge/WAF/Tunnel/R2) + Hostinger VPS Self-Hosting (`apps/api`, workers, PostgreSQL/Redis) + Supabase Auth + Multi-Provider Email (Resend, Emailbump, Unipost).
- Implemented features:
  - Phase 1: Secure Foundation (Supabase Auth JWT verification, multi-tenant RBAC, PostgreSQL RLS baseline, tamper-evident hash-chained audit service, Resend/Emailbump/Unipost email adapter, SDLC/DevOps pipelines).
  - Phase 2: Recording and Media (Meeting creation & participant roster, mandatory pre-recording notice & host confirmation gate, browser microphone recorder state machine & unload guard, resumable chunked upload with SHA-256 & magic-byte validation, private tenant-prefixed storage, asynchronous media validation/normalisation worker preserving original media separately from derivatives, and short-lived signed playback URLs).
- Known blockers: None for Phase 2. Voice cloning remains disabled by feature flag (`VOICE_CLONING_ENABLED=false`) pending Phase 6 governance gates.
- Next approved task: Phase 3 — Transcription (`prompts/phases/03_PHASE_TRANSCRIPTION.md`).
