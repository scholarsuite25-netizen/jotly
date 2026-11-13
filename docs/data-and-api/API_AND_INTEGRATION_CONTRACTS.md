# 04 — API and Integration Contracts

## 1. API conventions
- Prefix: `/api/v1`.
- JSON request/response schemas with validation.
- Authenticated identity and tenant membership resolved server-side.
- Enforce resource-level permissions on every endpoint.
- Return asynchronous job IDs for long-running work.
- Support idempotency keys for uploads, exports, and synthesis.
- Apply rate limits and tenant quotas to expensive operations.
- Use short-lived signed URLs for object transfer.
- Never return storage credentials, model credentials, or unrestricted object URLs.
- Use consistent error envelopes and correlation IDs.
- Document endpoints using OpenAPI.

## 2. Initial endpoint catalogue

| Area | Method and path | Purpose |
|---|---|---|
| Health | `GET /api/v1/health`, `GET /api/v1/ready` | Service & deployment readiness check |
| Identity | `GET /api/v1/me` | Current Supabase Auth identity, verified organisations, active tenant & permissions |
| Organisations | `POST /api/v1/organisations`, `GET /api/v1/organisations/{org_id}` | Create/read organisation with default RBAC roles |
| Workspaces | `POST /api/v1/organisations/{org_id}/workspaces`, `GET /api/v1/organisations/{org_id}/workspaces` | Manage tenant-isolated workspaces |
| Invitations | `POST /api/v1/organisations/{org_id}/invitations` | Invite member & send email via Resend/Emailbump/Unipost adapter |
| Jobs | `GET /api/v1/jobs/{job_id}`, `POST /api/v1/jobs/{job_id}/cancel` | Tenant-isolated background job status & cancellation |
| Audit | `GET /api/v1/audit-events`, `GET /api/v1/audit-events/verify` | Retrieve permitted audit records & verify tamper-evident hash chain |
| Meetings | `POST /api/v1/meetings`, `GET /api/v1/meetings`, `GET /api/v1/meetings/{id}` | Create/read meeting metadata & attendees |
| Recording Notice | `POST /api/v1/meetings/{id}/recording-notice-confirm` | Record host confirmation of recording notice & consent reminder |
| Upload Session | `POST /api/v1/meetings/{id}/uploads`, `GET /api/v1/meetings/{id}/uploads/{session_id}` | Create & inspect resumable upload session |
| Upload Chunks | `PUT /api/v1/meetings/{id}/uploads/{session_id}/chunks/{chunk_index}` | Upload checksum-verified & signature-validated chunk |
| Upload Finalise | `POST /api/v1/meetings/{id}/uploads/{session_id}/complete` | Verify manifest, assemble original media, queue normalisation worker |
| Media & Playback | `GET /api/v1/meetings/{id}/media`, `GET /api/v1/media/{asset_id}/playback-url`, `GET /api/v1/media/{asset_id}/stream` | List assets/derivatives & issue/verify short-lived signed playback URLs |
| Transcript | `GET /api/v1/transcripts/{id}` | Fetch authorised transcript with segments, speaker suggestions & revision metadata |
| Transcription | `POST /api/v1/media/{id}/transcriptions` | Queue idempotent ASR job; execute in isolated worker tenant context |
| Transcript edit | `PATCH /api/v1/transcripts/{id}/segments/{segment_id}`, `POST .../undo`, `POST .../find-replace`, `POST .../speakers/{speaker_id}/relabel` | Edit segments with immutable revision history, undo, bulk replace & speaker relabel |
| Export | `POST /api/v1/transcripts/{id}/exports`, `GET /api/v1/transcripts/{id}/exports`, `POST /api/v1/transcripts/{id}/evaluation` | Create TXT/SRT/VTT exports, list export-ready data, and run WER evaluation harness |
| Document ingest | `POST /api/v1/documents` | Upload and extract document |
| TTS | `POST /api/v1/speech-projects` | Create speech job |
| Voice consent | `POST /api/v1/voice-consents` | Record consent/authorisation |
| Voice profile | `POST /api/v1/voice-profiles` | Create after consent validation |
| Synthesis | `POST /api/v1/voice-profiles/{id}/synthesis` | Generate only after permission checks |
| Search | `POST /api/v1/search` | Permission-filtered search |
| Assistant | `POST /api/v1/assistant/questions` | Ask authorised sources |

## 3. Upload protocol
1. Client requests upload session for an authorised meeting/document.
2. API validates permission, file size, type, quota, and policy.
3. API creates a session and issues short-lived upload authorisation.
4. Client uploads chunks; each chunk is checksum-validated.
5. Client finalises upload.
6. API verifies chunk manifest and object integrity.
7. API creates media/document record and queues processing.
8. Worker validates content in an isolated processing environment.
9. Client polls or subscribes to job status.

Duplicate chunk/finalise requests must be idempotent.

## 4. Job API pattern
- Create: returns `202 Accepted`, `job_id`, initial status.
- Read: returns status, progress, timestamps, safe error details.
- Cancel: allowed only when job state and permissions permit.
- Retry: controlled by server policy; no duplicate side effects.
- Completion: output references are authorised independently.

## 5. Integrations
Calendar, conferencing, storage, identity, and notification providers must be implemented through narrow adapters. Each integration requires:
- documented scopes and consent
- secret storage and rotation
- webhook signature verification
- replay protection
- timeout/retry policy
- tenant-level enable/disable
- audit trail
- provider terms review

## 6. API security tests
Test unauthenticated calls, cross-tenant IDs, role escalation, stale signed URLs, replayed webhooks, oversized uploads, invalid MIME types, job ID guessing, rate-limit bypass, and revoked voice permission.
