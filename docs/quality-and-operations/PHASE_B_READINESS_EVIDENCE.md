# Phase B Readiness Evidence (Vercel-first)

**Product:** NEXUS Meeting Intelligence (Jotly)  
**Scope:** Evidence collected for Phase B operational/release-readiness progression under **ADR-006 (Vercel-first deployment, stubbed real inference on Vercel)**. This document records **automated/live checks and verified flows only**; it does not replace owner-operated gates.

**Environment (verified):**
- Production app/API: `https://jotly-sigma.vercel.app` (`/api/v1` routed to FastAPI; `/api/v1/health` → `{"status":"ok"}`)
- Supabase project: `izxneacavxfcjklnsftd` (Auth + Postgres pooler + S3-compatible storage), schema at `0008_phase8_collaboration`
- Storage: private bucket `nexus-private-media` exists (`head_bucket` OK)
- Test/admin identity (verified): `samuel@jotly.org.ng`, organisation **Jotly** (`2a59a56c-97aa-46a3-880e-f5777fa02f88`, `organisation_admin`), workspace **General Workspace**
- Voice cloning: **locked off** (`VOICE_CLONING_ENABLED=false`)

## 1. Automated release-readiness report (live)

Source: `GET /api/v1/release/readiness-report` (tenant admin context)  
Captured: `generated_at 2026-11-14T11:53:07.242565+00:00`, organisation `2a59a56c-97aa-46a3-880e-f5777fa02f88`

| Check | Severity | Passed | Evidence |
|---|---|---:|---|
| `voice_cloning_public_gate_disabled` | blocker_if_failed | true | `VOICE_CLONING_ENABLED=False` |
| `postgres_rls_enabled_and_forced_on_all_tenant_tables` | blocker_if_failed | true | Verified 50 tables live via `pg_class` |
| `audit_hash_chain_integrity` | blocker_if_failed | true | Verified 13 chained audit entries for organisation |
| `transactional_email_failover_chain` | high_if_failed | true | Configured provider chain: `['resend', 'emailbump', 'unipost']` |
| `signed_playback_url_ttl_bounded` | high_if_failed | true | `S3_PRESIGNED_URL_TTL_SECONDS=300` |
| `server_side_tenant_resolution_enforced` | blocker_if_failed | true | Tenant membership resolved server-side via authenticated roles; client org headers not trusted |
| `human_review_approval_workflows_available` | medium_if_failed | true | Approval workflow resources operational (seed data present: False) |

- **Overall recommendation:** `GO` (automated checks only)
- **Report sign-off note:** Automated live checks only. Penetration testing, load benchmarks on target hardware, backup/restore drills, and legal/licence review remain owner-operated gates before production launch.

## 2. Frontend automated tests

Command: `cd apps/web && npm test`  
Result: **10 passed, 0 failed**

Coverage (suite highlights): auth-session store/clear/expiry preview, sign-in flow, organisation selection/headers, authenticated API headers, recorder state machine (notice gate, record/pause/resume/stop/upload/saved), transcript editor (edit/undo/revisions, find-replace preview/apply preserving original ASR), diarisation labels rendered as model suggestions (not identity-verified).

## 3. Production API end-to-end pipeline (verified)

Executed against `https://jotly-sigma.vercel.app/api/v1` (authenticated tenant admin). Demonstrates storage-backed media, validation, transcription job execution, transcript revision/edit, and export.

- **Meeting/notice:** `meeting_id da231ce5-6823-4e60-b858-596d9adb32db`, `recording_state notice_confirmed`
- **Upload/media:** upload session `d9338adc-bcc1-4eef-9c66-0024997fa954`, chunk uploaded (SHA-256 prefix `643f8a8dc8bd`), complete `status validated`, media asset `0916e6ee-e9e3-49b6-877b-f48cf3fe01f9` (`validated`, `idempotent_replay:false`, `media_count:1`)
- **Transcription:** job `62be0b44-8545-4123-8d3c-f9df5a1e9bb1` (`queued`→executed) → transcript `7cf0db4b-7ec4-4119-946f-a41b3c60f0dd` (`completed`, `stub-asr-deterministic`, `en`, 1 segment)
- **Edit/export:** segment edit `changed:true`, `revision:2`; TXT export `has_content:true`, `length:83`, preview `[0ms -> 1002ms] Unknown (edited): welcome everyone to the quarterly review [edited]`

**Constraint:** ASR/TTS/LLM inference on Vercel uses stub/deterministic adapters per ADR-006; accuracy/latency SLOs and real-model behavior are **not** evidenced here and are deferred to the self-hosted inference path.

## 4. In-browser UI smoke (partial, evidenced)

Verified on `https://jotly-sigma.vercel.app` (authenticated session):
- Dashboard rendered for `samuel@jotly.org.ng` / organisation **Jotly** with **Create meeting**, **Open transcript**, and **Meetings** sections (including transcript handoff helper text in latest UI).
- Meeting creation action performed in UI; backend confirms meeting present: titles include `["Browser UI Smoke Meeting","E2E Upload Test","Smoke Test Meeting"]`.
- Recorder UI reached for **Browser UI Smoke Meeting** via **Record** action: recording-notice dialog/state displayed with host confirmation control. A UI defect (missing Bearer token on recorder notice/upload requests causing `Missing Bearer authentication token`) was identified and fixed in `apps/web/src/app/recorder-screen.jsx` (commit `c470bc0`, deployed `dpl_2e2p9wTjLWdSk11JcvRcZXa4nLcG`, READY); successful post-fix notice confirmation state transition requires manual browser confirmation.
- Transcript editor opened for `7cf0db4b-7ec4-4119-946f-a41b3c60f0dd`, showing detected language/model, find/replace, editable segment with undo, and TXT/SRT/VTT export controls.

**Not fully automated/evidenced in-browser (manual confirmation required):** live microphone permission/capture → in-browser record/upload flow and a complete single-pass click-through including media playback and export download in the browser UI. Browser automation in this environment was limited by UI re-renders/stale element refs; pipeline correctness is corroborated by production API E2E above.

## 5. Deployment/configuration notes (Vercel-first)

- Monorepo routing via `vercel.json` (`/api/*` → `apps/api`, `/*` → `apps/web`), production deployment ready (latest relevant commits include `c470bc0`, `fe8fca3`, `ab848ed`, `c60b2e5`, `f00b74c`, `baaf645`).
- Backend configured with Supabase DB/JWT and S3-compatible storage env vars; `EMAIL_DRY_RUN=true` in current Vercel config. Frontend uses inlined `NEXT_PUBLIC_*` and same-origin `/api/v1` base.
- Health endpoint OK; auth (`/api/v1/me`) resolves server-side tenant membership.
- API contract inventory: `GET /api/v1/release/openapi-contract-summary` → `endpoint_count: 72` (authenticated admin).

## 6. Gaps and outstanding items (Phase B)

| Area | Status | Notes / next action |
|---|---|---|
| In-browser full click-through (incl. mic record/upload, playback, export download) | **Manual evidence needed** | Operator to perform and record screenshots/notes; fix any UI issues found. |
| Storage/CORS/origins/policy review | **Pending evidence** | Confirm Supabase bucket privacy/policies and allowed origins for Vercel production domain. |
| Backup posture (RPO/RTO) | **Pending evidence** | Document Supabase/Postgres backup configuration and retention; schedule restore drill. |
| Cross-tenant adversarial tests on live topology | **Pending** | Execute per `TESTING_AND_ACCEPTANCE.md` (API/search/object/job/ID isolation). |
| Retention/deletion evidence | **Pending** | Demonstrate delete flow and audit/retention evidence for test recording. |
| Operational runbooks/monitoring validation | **Pending** | Validate health/readiness/alerts/log hygiene per `DEPLOYMENT_AND_OPERATIONS.md`. |
| Real-model accuracy/latency/load | **Deferred (ADR-006)** | Stub inference on Vercel; benchmark on target self-hosted hardware with selected models. |

## 7. Phase C — owner-operated gates (outstanding)

Per readiness report and project governance (must be completed/approved by owners/third parties as applicable):
- Penetration test and adversarial cross-tenant review on production topology
- Load/performance benchmarks on Hostinger VPS hardware with selected models
- Backup/restore drill with defined RPO/RTO
- Model and dependency licence register final legal review (`SBOM_AND_LICENCE_REGISTER.md`, `OPEN_SOURCE_AND_LICENCE_GOVERNANCE.md`)
- Recording consent workflow legal review per target jurisdiction
- Go-live sign-off

## 8. Security/operational hygiene (action items)
- Revoke/rotate any Vercel API token previously shared in chat; avoid storing secrets in committed files or `NEXT_PUBLIC_*` variables.
- Rotate credentials exposed in prior local artifacts/commits if applicable.
- Keep `VOICE_CLONING_ENABLED=false` until all consent/verification/licensing/abuse-prevention gates are approved and tested.
