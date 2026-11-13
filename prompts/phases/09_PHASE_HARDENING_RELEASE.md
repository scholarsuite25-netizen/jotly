# Phase Prompt — Phase 9: Hardening and Release Readiness (OpenCode Lead / Antigravity Review)

Perform a release-readiness review; do not claim production readiness without evidence.

Check:
- threat model and security controls
- tenant isolation in API, DB, search, object storage, caches, queues, and AI retrieval
- dependency scanning, SBOM, model and asset licence register
- consent and privacy notices reviewed for target jurisdictions
- upload/parser security
- rate limits, quotas, bounded queues, tenant fairness
- load tests and model benchmarks on target hardware
- encryption, secrets, MFA/SSO, audit
- backup and restore drills; RPO/RTO
- monitoring, alerts, incident response, support runbooks
- application/schema/model rollback
- accessibility and responsive UI
- DOCX/PDF visual regression
- voice-clone public feature flag remains disabled unless every launch gate has formal approval

Produce a signed-off gap report with severity, owner, remediation, evidence, and go/no-go recommendation.
