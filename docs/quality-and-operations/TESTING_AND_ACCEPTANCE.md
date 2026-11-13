# 10 — Testing Strategy and Acceptance Criteria

## 1. Test layers
- Unit tests: domain logic, permissions, validators, job state machines.
- Integration tests: PostgreSQL/RLS, Redis, object storage, model adapters.
- API tests: authentication, authorisation, validation, idempotency, rate limits.
- UI tests: Vitest/component tests and Playwright flows.
- Security tests: cross-tenant, IDOR, upload, storage, prompt injection, voice consent.
- Performance tests: upload, queue, ASR, TTS, search, concurrency.
- Visual regression: DOCX/PDF output and responsive layouts.
- Recovery tests: backup restore, worker outage, retry, rollback.

## 2. Acceptance matrix

| Area | Acceptance |
|---|---|
| Recording | Start/pause/resume/stop; interrupted upload recovers; original audio retained; state clear |
| Transcription | Supported formats work; timestamps retained; failures reported; accuracy measured on documented set |
| Diarisation | Labels editable; uncertain labels never presented as verified identity |
| DOCX/PDF | Opens in common readers; page breaks, headers, tables, special characters pass visual checks |
| Document ingest | Long files, tables, scanned pages handled with clear OCR warnings |
| TTS | Audio playable; chunk joins acceptable; speed works; metadata correct |
| Voice consent | Cannot enrol/use without valid permission; revoked profile blocked |
| Tenant security | Tenant A cannot access tenant B via API, search, object URL, job ID, or guessed identifier |
| AI Q&A | Answers cite evidence; unsupported claims abstain; permissions applied before retrieval |
| Audit | Sensitive actions create tamper-evident audit records |
| Load | Queues bounded; tenant fairness; failures do not corrupt records |
| Recovery | Backup restore and disaster recovery exercised |

## 3. Required end-to-end scenario
1. Create two test organisations with separate administrators and users.
2. Create a meeting in organisation A.
3. Record a 15-minute sample with consenting speakers.
4. Upload, transcribe, review diarisation, and edit a segment.
5. Generate summary, minutes, decision register, and action list with evidence links.
6. Export DOCX and PDF; verify both render.
7. Upload DOCX/PDF, extract and review text, generate speech using a standard voice.
8. If clone functionality is enabled in the test environment, enrol only a consenting test speaker and inspect disclosure/audit.
9. Revoke permission and prove further synthesis is denied.
10. Ask an answerable and an unanswerable assistant question; verify citation and abstention.
11. Attempt cross-tenant access from organisation B; confirm denial.
12. Delete a test recording and verify retention/deletion evidence.

## 4. Metrics
- Speech recognition WER split by language/accent/noise/meeting type.
- Diarisation error rate and human correction time.
- Real-time factor and queue wait by hardware/model/duration.
- TTS intelligibility, naturalness, pronunciation, chunk continuity.
- Export reliability and visual correctness.
- Availability and job completion by service tier.
- Zero cross-tenant access in adversarial tests.
- No unresolved critical/high security findings at launch.
- User value: time saved, edit time per transcript hour, repeat usage, satisfaction.

## 5. Numeric targets
Set numeric SLOs only after baseline tests on selected infrastructure. Do not promise accuracy, latency, concurrency, or uptime without measured evidence.
