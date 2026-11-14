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
- Current release/milestone: Phase 10 — Frontend UI foundation (Completed). Phases 1–9 implemented and merged.
- Active branch: `feat/phase-10-frontend-ui` (to merge into `main`)
- Approved delivery & hosting path: OpenCode → GitHub (CI/CD, SDLC gates) → Vercel (`apps/web`) + Cloudflare (Backend Edge/WAF/Tunnel/R2) + Hostinger VPS Self-Hosting (`apps/api`, workers, PostgreSQL/Redis) + Supabase Auth + Multi-Provider Email (Resend, Emailbump, Unipost).
- Frontend UI screens added (Phase 10): sign-in screen (Supabase Auth via lib adapter, server-verified), organisation selection view model, dashboard (meeting list + signed playback links), recorder screen (notice gate → capture → resumable chunked upload), transcript editor screen (segment edit/undo, speaker relabel rendered as model suggestion, find/replace, TXT/SRT/VTT downloads). Auth-session lib adds token storage + client-side expiry preview (server remains the only authority).
- Implemented features:
  - Phase 1: Secure Foundation (Supabase Auth JWT verification, multi-tenant RBAC, PostgreSQL RLS baseline, tamper-evident hash-chained audit, Resend/Emailbump/Unipost email adapter, GitHub Actions SDLC gates).
  - Phase 2: Recording and Media (meetings + participant roster, recording-notice gate, recorder state machine, resumable chunked uploads with checksum & magic-byte validation, private tenant storage, media validation worker, short-lived signed playback URLs).
  - Phase 3: Transcription (replaceable ASR adapter + faster-whisper production path, idempotent jobs, timestamped/confidence segments, suggestion-only diarisation, revision-tracked editing/undo/relabel/find-replace, TXT/SRT/VTT exports, WER harness).
  - Phase 4: Document Studio (DOCX/PDF/TXT ingest with OCR detection + review warnings, branded DOCX/PDF/TXT exports with templates, confidentiality labels, source-linked versioning).
  - Phase 5: Voice Studio (standard TTS adapter, chunked synthesis, chapter markers, loudness normalisation, pronunciation dictionary, synthetic-audio disclosure).
  - Phase 6: Voice Governance (consent + verification enrolment, private-by-default profiles, owner permission grants with expiry, immediate revocation blocking, voice audit trail; public flag locked OFF).
  - Phase 7: Meeting Intelligence (permission-filtered retrieval before LLM, evidence-linked summaries/decisions/actions, grounded Q&A with abstention, prompt-injection detection, human review gate).
  - Phase 8: Collaboration (comments, revocable share grants, privacy-safe notifications, approval workflows with self-approval denial, action assignments, HMAC-signed webhooks with replay protection).
  - Phase 9: Hardening (automated release-readiness report with live checks: voice gate, RLS inventory, audit chain integrity, email failover, URL TTL bounds; contract inventory of 25+ endpoints; go/no-go recommendation; owner-operated gates enumerated).
- Known blockers: None in code. Production launch still requires owner gates: penetration test, load benchmarks on Hostinger hardware, backup/restore drill, model/dependency licence legal review, jurisdiction consent review. PostgreSQL RLS verification runs live in CI/production (SQLite test dialect defers it by design).
- Next approved task: Owner sign-off on release gate; deployment to Vercel/Cloudflare/Hostinger.
