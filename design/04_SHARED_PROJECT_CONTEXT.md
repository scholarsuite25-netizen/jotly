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
- Current release/milestone: **Phase 10 — Frontend UI wired for Vercel-first end-to-end flow (in progress)**. Phases 1–9 implemented and merged; Vercel-first deployment (ADR-006) live with Supabase Postgres/Storage integration configured.
- Active branch: `main` (Vercel-first deploy + Phase 10 wiring commits pushed; prior phase branches merged historically).
- Approved delivery & hosting path (ADR-006, Vercel-first): OpenCode → GitHub → **Vercel** (`apps/web` + `apps/api` via root `vercel.json`, `/api/*` routed to API) + **Supabase** (Auth, Postgres pooler, S3-compatible private storage). Cloudflare/Hostinger self-hosting and real model inference remain deferred until after Vercel-first testing.
- Frontend UI (Phase 10): sign-in (Supabase Auth, server-verified `/api/v1/me`), session restore, **organisation creation/selection**, authenticated app shell with navigation to **Dashboard / Recorder / Transcript editor**. Dashboard supports workspace-aware meeting creation/listing, **per-meeting media + transcript discovery (Media/Transcripts columns, "Open latest", explicit empty states)**, playback link retrieval, transcription start/open, and transcript open-by-id. Session-expiry (401) errors return the user to sign-in cleanly. Recorder confirms notice via backend API (auth headers attached) and performs resumable chunked upload. Transcript editor supports segment edit/undo, speaker relabel (suggestion-only), find/replace, and TXT/SRT/VTT exports.
- Implemented features (summary):
  - Phase 1: Secure Foundation (Supabase Auth JWT verification incl. ES256/JWKS, multi-tenant RBAC, PostgreSQL RLS, tamper-evident hash-chained audit, Resend/Emailbump/Unipost email adapter, CI/SDLC gates).
  - Phase 2: Recording and Media (meetings + participant roster, recording-notice gate, recorder state machine, resumable chunked uploads with checksum & magic-byte validation, private tenant storage, media validation worker, short-lived signed playback URLs).
  - Phase 3: Transcription (replaceable ASR adapter, idempotent jobs, timestamped/confidence segments, suggestion-only diarisation, revision-tracked editing/undo/relabel/find-replace, TXT/SRT/VTT exports, WER harness).
  - Phase 4: Document Studio (DOCX/PDF/TXT ingest with OCR detection + review warnings, branded exports with templates, confidentiality labels, source-linked versioning).
  - Phase 5: Voice Studio (standard TTS adapter, chunked synthesis, chapter markers, loudness normalisation, pronunciation dictionary, synthetic-audio disclosure).
  - Phase 6: Voice Governance (consent + verification enrolment, private-by-default profiles, owner permission grants with expiry, immediate revocation blocking, voice audit trail; public flag locked OFF).
  - Phase 7: Meeting Intelligence (permission-filtered retrieval before LLM, evidence-linked summaries/decisions/actions, grounded Q&A with abstention, prompt-injection detection, human review gate).
  - Phase 8: Collaboration (comments, revocable share grants, privacy-safe notifications, approval workflows with self-approval denial, action assignments, HMAC-signed webhooks with replay protection).
  - Phase 9: Hardening (automated release-readiness report with live checks; contract inventory; go/no-go recommendation; owner-operated gates enumerated).
- Deployment & verification (evidence in session): Vercel production deployed (`https://jotly-sigma.vercel.app`, latest ready deployment includes UI wiring + auth fixes + per-meeting discovery), `/api/v1/health` OK, Supabase-backed auth/`/api/v1/me` OK, admin user + organisation (`Jotly`, `organisation_admin`) provisioned, API smoke test passed (workspace list, meeting create, recording-notice confirm), per-meeting transcript listing endpoint live-verified. Tests passing locally: backend `53`, frontend `16`.
- Known blockers / operator actions: **Supabase Storage private bucket `nexus-private-media` must exist** (not verifiable from this environment) for upload/playback persistence; real STT/TTS/LLM accuracy deferred on Vercel (stub adapters per ADR-006). Owner gates remain: penetration test, load/benchmark, backup/restore drill, model/dependency licence legal review, jurisdiction/consent review. Rotate/revoke any shared Vercel tokens and consider rotating DB credentials exposed in prior local artifacts/commits if applicable.
- Next approved task: complete end-to-end browser smoke on Vercel (including media upload/transcription/export once storage bucket is confirmed), refine dashboard/meeting-detail transcript discovery UX, then progress release-gate evidence and owner-operated readiness items.
