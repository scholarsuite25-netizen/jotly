# 05 — Security Baseline and Threat Model

## 1. Security objectives
Protect meeting content, personal data, voice samples, derived voice representations, documents, credentials, and tenant boundaries. Maintain confidentiality, integrity, availability, traceability, and recoverability.

## 2. Minimum controls
- TLS for all network traffic.
- Encryption at rest for database, object storage, and backups.
- MFA for administrators; SSO support for enterprise.
- Tenant isolation in API, database, object storage, search, cache, queues, and AI retrieval.
- Least-privilege service accounts.
- Secrets manager, rotation, and no secrets in source control/client bundles.
- Audit access, playback, export, sharing, clone enrolment, synthesis, revocation, and deletion.
- Upload size/content-type validation, malware scanning, and sandboxed parsers.
- Encrypted backups and tested restore.
- Incident response, vulnerability management, dependency scanning, penetration testing, and patch SLAs.
- Data minimisation, retention, access/export/deletion workflows, and legal hold.
- Recording notices and consent appropriate to the jurisdiction and meeting context.

## 3. Threat scenarios and controls

| Threat | Example | Required controls |
|---|---|---|
| Cross-tenant data exposure | User guesses another tenant's transcript ID | RLS, server authorisation, object policy, adversarial tests |
| Credential compromise | Admin account takeover | MFA, secure sessions, alerts, least privilege |
| Malicious upload | Parser exploit or malware | MIME/signature checks, scanning, sandbox, limits |
| Storage URL leakage | Long-lived public media link | Private buckets, short-lived signed URLs, audit |
| Queue isolation failure | Worker processes wrong tenant context | Explicit tenant context, scoped credentials, tests |
| Prompt injection | Transcript tells assistant to reveal data | Treat content as untrusted; narrow typed tools |
| Voice impersonation | Unauthorised clone enrolment/use | Owner consent, verification, private profiles, revocation |
| Insider misuse | Staff accesses confidential board recording | Least privilege, break-glass, immutable/tamper-evident audit |
| Data loss | Storage/database failure | Encrypted backups, restore drills, RPO/RTO |
| Denial of service | Very long files or excessive jobs | Quotas, bounded queues, concurrency limits, rate limits |

## 4. AI and worker boundaries
- Do not allow model output to run arbitrary SQL, shell commands, or unrestricted tools.
- Expose only typed, narrow server-side functions.
- Uploaded documents and transcripts are untrusted data, never instructions to override system policy.
- Keep model endpoints private and credentials server-side.
- Use resource limits and isolated workers for untrusted file processing.

## 5. Audit events
At minimum record actor, tenant, action, resource, result, timestamp, correlation ID, and policy-relevant context. Avoid storing transcript text, raw voice samples, passwords, tokens, or unnecessary personal data in logs.

## 6. Release security gate
No production release with unresolved critical/high vulnerabilities. Complete threat review, tenant isolation tests, dependency/model licence review, restore test, and incident-response readiness.
