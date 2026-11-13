# 02 — Implementation Roadmap

## Delivery approach
Build one end-to-end vertical slice at a time. Each phase requires code review, automated tests, manual acceptance, security checks, and updated documentation. AI-generated code is not evidence of completion.

| Phase | Scope | Exit criteria |
|---|---|---|
| 0. Discovery | Personas, jurisdictions, recording contexts, formats, consent, retention, pilot hardware, risk register | Approved requirements, architecture decisions, backlog and threat model |
| 1. Foundation | Repository, CI, Docker, database, identity, tenancy, permissions, audit baseline | Secure login, organisation creation, migrations, cross-tenant denial tests |
| 2. Recording & media | Browser microphone, state handling, chunked upload, playback, media library | Reliable capture/upload, interruption recovery, original media lifecycle |
| 3. Transcription | Local ASR adapter, language, timestamps, transcript editor, revisions | Tested transcript pipeline and documented evaluation corpus |
| 4. Documents | DOCX/PDF/TXT ingest, OCR detection, templates, DOCX/PDF exports | Reliable editable and printable document workflows |
| 5. Voice Studio | Standard TTS, chunking, playback, audio export | Long-document TTS works for declared supported languages |
| 6. Voice cloning | Consent, verification, profile, OpenVoice evaluation, permission, revocation, audit | No unauthorised creation/use; quality and abuse tests passed |
| 7. Meeting intelligence | Summaries, minutes, decisions, actions, evidence-grounded Q&A | Human-reviewed outputs with valid source references |
| 8. Collaboration | Teams, sharing, comments, notifications, approval, SSO | Permission and workflow tests pass |
| 9. Hardening & launch | Pen/load tests, backup/restore, monitoring, docs, support, rollback | Production readiness sign-off |

## Recommended proof of concept
1. Create two organisations and users with different permissions.
2. Record a 5–10 minute test meeting using browser microphone.
3. Upload and transcribe using a local Whisper-family model.
4. Review timestamps and speaker labels; edit one segment.
5. Generate DOCX and PDF transcript.
6. Upload DOCX, extract text, synthesize with a standard TTS voice.
7. Play and download audio; verify duration and metadata.
8. Use only a consenting test speaker if voice-clone PoC is included.
9. Revoke the test clone and prove further use is blocked.
10. Attempt cross-tenant access and inspect audit records.

This validates the technical spine, not production readiness.

## Definition of phase complete
- Scope implemented behind the correct permission boundary.
- Migrations reviewed and tested.
- Unit, integration, and end-to-end tests pass.
- Negative security tests pass.
- Human acceptance criteria are demonstrated.
- Logs/metrics and failure handling exist.
- User/admin documentation updated.
- Known gaps and rollback steps documented.
- No unresolved critical/high security issues for a production-bound phase.

## Suggested backlog order
1. Repository and architecture review
2. Authentication and organisation membership
3. RLS and server-side permission middleware
4. Audit event framework
5. Meeting metadata and browser recorder
6. Resumable uploads and private object storage
7. Media validation and playback
8. ASR job orchestration
9. Transcript review/revisions
10. DOCX/PDF exports
11. Document ingest and OCR detection
12. Standard TTS
13. RAG meeting assistant
14. Voice clone governance and controlled evaluation
15. Collaboration and integrations
16. Production hardening
